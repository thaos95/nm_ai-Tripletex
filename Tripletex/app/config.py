from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: Optional[str] = Field(default=None, alias="TRIPLETEX_AGENT_API_KEY")
    verify_tls: bool = Field(default=True, alias="TRIPLETEX_VERIFY_TLS")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    enable_preflight: bool = Field(default=False, alias="TRIPLETEX_ENABLE_PREFLIGHT")
    enable_bank_account_creation: bool = Field(
        default=False, alias="TRIPLETEX_ENABLE_BANK_ACCOUNT_CREATION"
    )
    default_bank_account_number: Optional[str] = Field(
        default=None, alias="TRIPLETEX_DEFAULT_BANK_ACCOUNT_NUMBER"
    )
    default_bank_account_name: Optional[str] = Field(
        default=None, alias="TRIPLETEX_DEFAULT_BANK_ACCOUNT_NAME"
    )
    default_bank_account_type: Optional[str] = Field(
        default=None, alias="TRIPLETEX_DEFAULT_BANK_ACCOUNT_TYPE"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
