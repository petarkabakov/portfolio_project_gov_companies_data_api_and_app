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
