from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keitaro_url: str = "https://keitaro-for-tests.etolegko.com"
    keitaro_api_key: str = ""

    keitaro_domain_id: int = 1813
    keitaro_group_id: int = 10332
    keitaro_traffic_source_id: int = 836

    geo_redirect_url: str = "https://google.com"

    database_url: str = "sqlite:///./keitaro_wrapper.db"

    @property
    def keitaro_api_base(self) -> str:
        return self.keitaro_url.rstrip("/") + "/admin_api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
