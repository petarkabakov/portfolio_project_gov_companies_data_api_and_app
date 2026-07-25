from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    companies_house_api_key: str
    companies_house_base_url: str = "https://api.company-information.service.gov.uk"
    database_url: str

    rate_limit_max_requests: int = 600
    rate_limit_window_seconds: float = 300.0
    request_timeout_seconds: float = 10.0
    retry_max_attempts: int = 5
