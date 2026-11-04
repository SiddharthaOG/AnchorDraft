"""Application configuration."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    VERSION: str = "0.1.0"
    ALLOWED_ORIGINS: list[str] = []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get settings instance (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (for testing)."""
    get_settings.cache_clear()


settings = get_settings()