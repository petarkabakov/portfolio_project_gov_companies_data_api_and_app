import logging
from collections.abc import Iterator

import httpx
from pydantic import ValidationError
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from registry_sentinel.clock import Clock, RealClock
from registry_sentinel.config import Settings
from registry_sentinel.exceptions import (
    AuthenticationError,
    CompaniesHouseAPIError,
    CompanyNotFoundError,
    RetriableStatusError,
)
from registry_sentinel.models import (
    CompanyOfficer,
    CompanyProfile,
    CompanySearchResult,
    PersonWithSignificantControl,
)
from registry_sentinel.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_exponential_backoff = wait_exponential_jitter(initial=1, max=30)


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _wait_retry_after_or_backoff(retry_state: RetryCallState) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, RetriableStatusError) and exc.retry_after is not None:
        return exc.retry_after
    return _exponential_backoff(retry_state)


class CompaniesHouseClient:
    """Sync Companies House client: rate-limited, retried, and clock-driven.

    Adding a new endpoint is a new thin method + model, not a rewrite of this
    plumbing — auth/rate-limit/retry/pagination all live in _paginate,
    _do_request, and _raise_for_status.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._clock = clock or RealClock()
        self._rate_limiter = RateLimiter(
            self._clock,
            max_requests=settings.rate_limit_max_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        self._http = httpx.Client(
            base_url=settings.companies_house_base_url,
            auth=(settings.companies_house_api_key, ""),
            timeout=settings.request_timeout_seconds,
            transport=transport,
        )
        self._retrying = Retrying(
            sleep=self._clock.sleep,
            stop=stop_after_attempt(settings.retry_max_attempts),
            wait=_wait_retry_after_or_backoff,
            retry=retry_if_exception_type((httpx.TransportError, RetriableStatusError)),
            reraise=True,
        )

    def __enter__(self) -> "CompaniesHouseClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._http.close()

    def get_company_profile(self, company_number: str) -> tuple[CompanyProfile, dict]:
        """Returns (validated model, raw JSON dict) — the raw dict is what gets persisted."""
        response = self._retrying(self._do_request, "GET", f"/company/{company_number}")
        payload = response.json()
        return CompanyProfile.model_validate(payload), payload

    def search_companies(
        self, query: str, *, page_size: int = 100
    ) -> Iterator[CompanySearchResult]:
        for item in self._paginate("/search/companies", params={"q": query}, page_size=page_size):
            yield CompanySearchResult.model_validate(item)

    def get_officers(
        self, company_number: str, *, page_size: int = 100
    ) -> Iterator[tuple[CompanyOfficer, dict]]:
        """Yields (validated model, raw JSON dict) per officer — the raw dict is
        what gets persisted. Unlike search_companies, a single unparseable
        officer is skipped-and-logged rather than propagated: one bad record in
        a list of many shouldn't abort the whole company's officer ingestion.
        """
        path = f"/company/{company_number}/officers"
        for item in self._paginate(path, params={}, page_size=page_size):
            try:
                yield CompanyOfficer.model_validate(item), item
            except ValidationError:
                logger.warning("skipping unparseable officer for %s", company_number)

    def get_pscs(
        self, company_number: str, *, page_size: int = 100
    ) -> Iterator[tuple[PersonWithSignificantControl, dict]]:
        """Yields (validated model, raw JSON dict) per PSC — same skip-and-log
        policy as get_officers, for the same reason.
        """
        path = f"/company/{company_number}/persons-with-significant-control"
        for item in self._paginate(path, params={}, page_size=page_size):
            try:
                yield PersonWithSignificantControl.model_validate(item), item
            except ValidationError:
                logger.warning("skipping unparseable PSC for %s", company_number)

    def _paginate(self, path: str, *, params: dict, page_size: int) -> Iterator[dict]:
        """Follows Companies House's start_index/items_per_page pagination
        convention, yielding every raw item dict across every page.

        Stops when a page comes back short of page_size or once start_index has
        reached the API's own total_results — whichever signal is available and
        fires first, so a missing/inconsistent total_results doesn't loop forever.
        """
        start_index = 0
        while True:
            response = self._retrying(
                self._do_request,
                "GET",
                path,
                params={**params, "start_index": start_index, "items_per_page": page_size},
            )
            payload = response.json()
            items = payload.get("items", [])
            yield from items

            if not items:
                return
            start_index += len(items)
            total_results = payload.get("total_results")
            if total_results is not None and start_index >= total_results:
                return
            if len(items) < page_size:
                return

    def _do_request(self, method: str, path: str, *, params: dict | None = None) -> httpx.Response:
        self._rate_limiter.acquire()
        response = self._http.request(method, path, params=params)
        self._reconcile_from_headers(response)
        self._raise_for_status(response)
        return response

    def _reconcile_from_headers(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-Ratelimit-Remain")
        reset = response.headers.get("X-Ratelimit-Reset")
        if remaining is not None and reset is not None:
            self._rate_limiter.observe_server_headers(
                remaining=int(remaining), reset_epoch=float(reset)
            )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 404:
            raise CompanyNotFoundError(f"company not found: {response.request.url}")
        if response.status_code == 401:
            raise AuthenticationError(f"authentication failed: {response.request.url}")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetriableStatusError(response, _parse_retry_after(response))
        if response.status_code >= 400:
            raise CompaniesHouseAPIError(
                f"unexpected status {response.status_code} for {response.request.url}"
            )
