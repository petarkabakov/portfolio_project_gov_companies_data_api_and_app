import httpx


class RegistrySentinelError(Exception):
    """Base class for all errors raised by this package."""


class CompanyNotFoundError(RegistrySentinelError):
    """Raised when Companies House returns 404 for a company number."""


class AuthenticationError(RegistrySentinelError):
    """Raised when Companies House returns 401 (bad or missing API key)."""


class CompaniesHouseAPIError(RegistrySentinelError):
    """Raised for unmapped, non-retriable API errors."""


class RetriableStatusError(RegistrySentinelError):
    """Wraps a 429/5xx response so tenacity can retry it."""

    def __init__(self, response: httpx.Response, retry_after: float | None):
        super().__init__(f"retriable status {response.status_code} for {response.request.url}")
        self.response = response
        self.retry_after = retry_after
