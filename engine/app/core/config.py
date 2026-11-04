"""Application configuration."""
import os
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


settings = Settings()