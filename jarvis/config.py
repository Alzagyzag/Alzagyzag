from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_", env_file=".env", extra="ignore")

    api_token: SecretStr = SecretStr("")
    provider: Literal["openai", "openai_compatible", "ollama"] = "openai"
    model: str = "gpt-4o-mini"
    provider_api_key: SecretStr = SecretStr("")
    provider_base_url: str = "https://api.openai.com/v1"
    database_path: str = "data/jarvis.sqlite3"
    request_timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_concurrent_requests: int = Field(default=4, ge=1, le=32)
    max_context_messages: int = Field(default=40, ge=2, le=200)
    personality: str = (
        "You are J.A.R.V.I.S., a composed, analytical assistant with subtle British humour. "
        "Be concise for simple questions and detailed when useful. Use 'sir' sparingly. "
        "Never claim to have performed an action unless verified. You have no computer "
        "control tools in this version. Provide brief decision summaries, not private reasoning."
    )

    def unavailable_reason(self) -> str | None:
        if not self.api_token.get_secret_value():
            return "JARVIS_API_TOKEN is required to enable authenticated assistant access."
        if self.provider != "ollama" and not self.provider_api_key.get_secret_value():
            return "JARVIS_PROVIDER_API_KEY is required for the selected provider."
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
