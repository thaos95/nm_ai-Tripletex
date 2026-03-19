from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: Optional[str] = Field(default=None, alias="TRIPLETEX_AGENT_API_KEY")
    verify_tls: bool = Field(default=True, alias="TRIPLETEX_VERIFY_TLS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
