from registry_sentinel.exceptions import AuthenticationError, CompanyNotFoundError
from registry_sentinel.ingest import ingest_batch


class FakeClient:
    def __init__(self, responses: dict, officers: dict | None = None, pscs: dict | None = None):
        self._responses = responses
        self._officers = officers or {}
        self._pscs = pscs or {}

    def get_company_profile(self, company_number: str):
        outcome = self._responses[company_number]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {"company_number": company_number}

    def get_officers(self, company_number: str):
        return iter(self._officers.get(company_number, []))

    def get_pscs(self, company_number: str):
        return iter(self._pscs.get(company_number, []))


class FakeRepository:
    def __init__(self):
        self.saved: list[str] = []
        self.saved_officers: list[tuple[str, str]] = []
        self.saved_pscs: list[tuple[str, str]] = []

    def save_company_profile(self, *, company_number, payload, fetched_at, http_status):
        self.saved.append(company_number)

    def save_officer(self, *, company_number, officer_id, payload, fetched_at, http_status):
        self.saved_officers.append((company_number, officer_id))

    def save_psc(self, *, company_number, psc_id, payload, fetched_at, http_status):
        self.saved_pscs.append((company_number, psc_id))


def _officer_raw(officer_id: str) -> dict:
    return {
        "name": "SMITH, Jane",
        "links": {"officer": {"appointments": f"/officers/{officer_id}/appointments"}},
    }


def _psc_raw(psc_id: str) -> dict:
    return {
        "kind": "individual-person-with-significant-control",
        "links": {"self": f"/psc/{psc_id}"},
    }


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


def test_officers_and_pscs_are_ingested_after_successful_profile_fetch():
    client = FakeClient(
        {"00000001": object()},
        officers={"00000001": [(object(), _officer_raw("off1")), (object(), _officer_raw("off2"))]},
        pscs={"00000001": [(object(), _psc_raw("psc1"))]},
    )
    repository = FakeRepository()

    results = ingest_batch(["00000001"], client=client, repository=repository)

    assert repository.saved_officers == [("00000001", "off1"), ("00000001", "off2")]
    assert repository.saved_pscs == [("00000001", "psc1")]
    assert results[0].officers_ingested == 2
    assert results[0].pscs_ingested == 1


def test_officers_and_pscs_are_not_fetched_when_profile_fails():
    client = FakeClient(
        {"00000001": CompanyNotFoundError("not found")},
        officers={"00000001": [(object(), _officer_raw("off1"))]},
    )
    repository = FakeRepository()

    ingest_batch(["00000001"], client=client, repository=repository)

    assert repository.saved_officers == []


def test_officer_with_unparseable_id_is_skipped():
    client = FakeClient(
        {"00000001": object()},
        officers={"00000001": [(object(), {"name": "SMITH, Jane", "links": {}})]},
    )
    repository = FakeRepository()

    results = ingest_batch(["00000001"], client=client, repository=repository)

    assert repository.saved_officers == []
    assert results[0].officers_ingested == 0
