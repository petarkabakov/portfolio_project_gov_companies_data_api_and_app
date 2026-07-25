from registry_sentinel.exceptions import AuthenticationError, CompanyNotFoundError
from registry_sentinel.ingest import ingest_batch


class FakeClient:
    def __init__(self, responses: dict):
        self._responses = responses

    def get_company_profile(self, company_number: str):
        outcome = self._responses[company_number]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {"company_number": company_number}


class FakeRepository:
    def __init__(self):
        self.saved: list[str] = []

    def save_snapshot(self, *, company_number, payload, fetched_at, http_status):
        self.saved.append(company_number)


def test_batch_mixing_success_and_failures_continues_past_errors():
    client = FakeClient(
        {
            "00000001": object(),
            "00000002": CompanyNotFoundError("not found"),
            "00000003": AuthenticationError("bad key"),
        }
    )
    repository = FakeRepository()

    results = ingest_batch(
        ["00000001", "00000002", "00000003"], client=client, repository=repository
    )

    assert repository.saved == ["00000001"]
    assert [r.ok for r in results] == [True, False, False]
    assert results[1].error == "not_found"
    assert "bad key" in results[2].error


def test_system_exit_only_raised_by_caller_when_everything_failed():
    client = FakeClient(
        {
            "00000001": CompanyNotFoundError("not found"),
            "00000002": CompanyNotFoundError("not found"),
        }
    )
    repository = FakeRepository()

    results = ingest_batch(["00000001", "00000002"], client=client, repository=repository)

    assert all(not r.ok for r in results)
    assert repository.saved == []


def test_empty_batch_returns_empty_results():
    results = ingest_batch([], client=FakeClient({}), repository=FakeRepository())

    assert results == []
