"""Application configuration."""
from functools import lru_cache
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_allowed_origins(value: Any) -> list[str]:
    """Parse ALLOWED_ORIGINS from env var.

    Accepts either a JSON array string (e.g., '["http://a","http://b"]')
    or a comma-separated string (e.g., 'http://a,http://b').
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        # Try JSON array first
        if value.startswith("[") and value.endswith("]"):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        # Fall back to comma-separated
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return []


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    VERSION: str = "0.1.0"
    # Store as string to avoid pydantic's JSON parsing of env vars
    ALLOWED_ORIGINS: str = ""

    # Supabase configuration
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_ISSUER: str = ""
    SUPABASE_AUDIENCE: str = "authenticated"

    # Database configuration
    DATABASE_URL: str = ""

    # Required for encrypting short-lived preview placeholder maps.
    PREVIEW_ENCRYPTION_KEY: str = ""

    # Rate limits and caps
    DAILY_REVIEW_CAP: int = 20
    PER_USER_RATE_LIMIT: int = 10
    REVISION_BODY_MAX_CHARS: int = 20000
    COMMENT_MAX_CHARS: int = 2000
    UPLOAD_MAX_MB: int = 5
    UPLOAD_MAX_PAGES: int = 20
    REQUEST_BODY_MAX_MB: int = 6

    # Engine version for review tracking
    ENGINE_VERSION: str = "0.1.0"

    # LLM Provider Configuration
    LLM_PROVIDER: str = "fake"
    LLM_FALLBACK_PROVIDER: str = "gemini"
    LLM_FALLBACK_ENABLED: bool = True

    # Environment (development, staging, production) - no default, must be explicitly set
    ENVIRONMENT: str

    # Groq settings
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TPM_LIMIT: int = 8000
    GROQ_RPM_LIMIT: int = 30

    # Gemini settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    # Distinct same-provider fallback for transient Gemini 3.8 capacity failures.
    GEMINI_FALLBACK_MODEL: str = "gemini-3.6-flash"
    GEMINI_TPM_LIMIT: int = 250000
    GEMINI_RPM_LIMIT: int = 15

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _ensure_string(cls, value: Any) -> str:
        # Ensure we always have a string for the raw value
        if value is None:
            return ""
        return str(value)

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def _normalize_environment(cls, value: Any) -> str:
        """Normalize and validate the deployment environment."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "ENVIRONMENT must be explicitly set to one of: "
                "development, dev, local, test, staging, production, prod"
            )

        normalized = value.strip().lower()

        allowed_environments = {
            "development",
            "dev",
            "local",
            "test",
            "staging",
            "production",
            "prod",
        }

        if normalized not in allowed_environments:
            raise ValueError(
                f"Unsupported ENVIRONMENT '{normalized}'. "
                f"Allowed values: {', '.join(sorted(allowed_environments))}"
            )

        return normalized

    @property
    def ALLOWED_ORIGINS_LIST(self) -> list[str]:
        """Parsed list of allowed origins."""
        return _parse_allowed_origins(self.ALLOWED_ORIGINS)

    @property
    def is_local_environment(self) -> bool:
        """Check if running in a local development environment where fake provider is allowed."""
        return self.ENVIRONMENT in ("development", "dev", "local", "test")

    @property
    def is_production_environment(self) -> bool:
        """Check if running in a production environment."""
        return self.ENVIRONMENT in ("production", "prod")

    @property
    def is_staging_environment(self) -> bool:
        """Check if running in a staging environment."""
        return self.ENVIRONMENT == "staging"

    @property
    def requires_real_provider(self) -> bool:
        """Check if environment requires real (non-fake) providers."""
        return not self.is_local_environment


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get settings instance (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (for testing)."""
    get_settings.cache_clear()