from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    asr_base_url: str = "https://api.groq.com/openai/v1"
    asr_api_key: str = ""
    asr_model: str = "whisper-large-v3"

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    auth_token: str = ""

    data_dir: str = "./data"

    binance_base_url: str = "https://api.binance.com"
    bybit_base_url: str = "https://api.bybit.com"

    kline_cache_ttl_seconds: int = 30

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:8000",
        ]
    )

    def __repr__(self) -> str:
        return (
            f"Settings(asr_base_url={self.asr_base_url!r}, "
            f"asr_model={self.asr_model!r}, "
            f"llm_base_url={self.llm_base_url!r}, "
            f"llm_model={self.llm_model!r}, "
            f"data_dir={self.data_dir!r}, "
            f"binance_base_url={self.binance_base_url!r}, "
            f"bybit_base_url={self.bybit_base_url!r}, "
            f"kline_cache_ttl_seconds={self.kline_cache_ttl_seconds!r}, "
            f"cors_origins={self.cors_origins!r})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
