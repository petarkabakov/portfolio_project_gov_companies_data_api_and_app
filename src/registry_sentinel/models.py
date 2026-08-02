"""Response models.

These are a lightweight "looks valid" gate, not a full field mapping: raw JSON
(not the model) is what gets persisted, so only the fields this pipeline
actually depends on are required. `extra="allow"` lets Companies House add
fields to the API over time without breaking ingestion.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_number: str
    company_name: str
    company_status: str | None = None
    type: str | None = None
    date_of_creation: date | None = None


class CompanySearchResult(BaseModel):
    """One item from the /search/companies results list."""

    model_config = ConfigDict(extra="allow")

    company_number: str
    title: str
    company_status: str | None = None
    company_type: str | None = None


class CompanyOfficer(BaseModel):
    """One item from the /company/{number}/officers results list.

    identity_verification_details is kept as an untyped passthrough dict, not
    sub-modeled: Companies House's own developer forum documents its shape as
    inconsistent between records (sometimes identity_verified_on plus the
    verifying ACSP's name, sometimes just a completion statement), with no
    canonical schema published as of this writing.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    officer_role: str | None = None
    appointed_on: date | None = None
    resigned_on: date | None = None
    links: dict | None = None
    identity_verification_details: dict | None = None


class PersonWithSignificantControl(BaseModel):
    """One item from the /company/{number}/persons-with-significant-control results list."""

    model_config = ConfigDict(extra="allow")

    kind: str
    name: str | None = None
    links: dict | None = None
    identity_verification_details: dict | None = None


def extract_officer_id(payload: dict) -> str | None:
    """Parses the only stable officer identifier Companies House exposes:
    links.officer.appointments, a URL like /officers/{officer_id}/appointments.
    """
    href = (payload.get("links") or {}).get("officer", {}).get("appointments")
    if not href:
        return None
    parts = href.rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 else None


def extract_psc_id(payload: dict) -> str | None:
    """Parses the psc_id out of links.self, e.g.
    /company/{number}/persons-with-significant-control/individual/{psc_id}.
    """
    href = (payload.get("links") or {}).get("self")
    if not href:
        return None
    return href.rstrip("/").split("/")[-1]
