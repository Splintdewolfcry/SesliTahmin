from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    asr_base_url: str = "https://api.groq.com/openai/v1"
    asr_api_key: SecretStr = SecretStr("")
    asr_model: str = "whisper-large-v3"

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4o-mini"

    auth_token: SecretStr = SecretStr("")

    data_dir: Path = Path("./data")

    binance_base_url: str = "https://api.binance.com"
    bybit_base_url: str = "https://api.bybit.com"

    kline_cache_ttl_seconds: int = 30

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:8000",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
