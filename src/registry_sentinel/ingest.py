"""Batch orchestration: fetch each company, persist its snapshot, and keep
going on a per-company failure — a batch of hundreds of company numbers will
routinely include dissolved companies (404) or transient errors, and one bad
number shouldn't abort the whole run. The process only exits non-zero when
every company failed, the practical signal for something systemic (bad auth,
network down) rather than a normal partial failure.
"""

import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from registry_sentinel.client import CompaniesHouseClient
from registry_sentinel.config import Settings
from registry_sentinel.exceptions import CompanyNotFoundError, RegistrySentinelError
from registry_sentinel.repository import CompanyProfileRepository

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    company_number: str
    ok: bool
    error: str | None = None


def ingest_batch(
    company_numbers: Iterable[str],
    *,
    client: CompaniesHouseClient,
    repository: CompanyProfileRepository,
) -> list[IngestResult]:
    results = []
    for number in company_numbers:
        try:
            _, raw = client.get_company_profile(number)
            repository.save_snapshot(
                company_number=number,
                payload=raw,
                fetched_at=datetime.now(timezone.utc),
                http_status=200,
            )
        except CompanyNotFoundError:
            logger.warning("company %s not found", number)
            results.append(IngestResult(number, ok=False, error="not_found"))
        except RegistrySentinelError as exc:
            logger.error("failed to ingest %s: %s", number, exc)
            results.append(IngestResult(number, ok=False, error=str(exc)))
        else:
            logger.info("ingested %s", number)
            results.append(IngestResult(number, ok=True))
    return results


def _load_company_numbers(path: str) -> list[str]:
    lines = Path(path).read_text().splitlines()
    return [line.strip() for line in lines if line.strip()]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m registry_sentinel.ingest <company_numbers_file>")

    settings = Settings()
    numbers = _load_company_numbers(sys.argv[1])

    with (
        CompaniesHouseClient(settings) as client,
        CompanyProfileRepository(settings.database_url) as repository,
    ):
        repository.ensure_schema()
        results = ingest_batch(numbers, client=client, repository=repository)

    ok = sum(result.ok for result in results)
    logger.info("batch complete: %d/%d succeeded", ok, len(results))
    if results and ok == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
