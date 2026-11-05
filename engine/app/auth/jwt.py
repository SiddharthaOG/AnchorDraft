"""JWT verification for Supabase tokens."""
import jwt
from jwt import PyJWKClient
from typing import Optional
from app.core.config import get_settings


class SupabaseJWTVerifier:
    """Verifies Supabase JWT tokens using JWKS."""

    # Explicit algorithm allowlist - never accept algorithm from token
    ALLOWED_ALGORITHMS = ["RS256"]

    def __init__(self):
        self._jwks_client: Optional[PyJWKClient] = None
        self._settings = get_settings()

    def _get_jwks_client(self) -> PyJWKClient:
        """Get or create the JWKS client."""
        if self._jwks_client is None:
            jwks_url = self._settings.SUPABASE_JWKS_URL
            if not jwks_url:
                raise RuntimeError("SUPABASE_JWKS_URL not configured")
            self._jwks_client = PyJWKClient(jwks_url)
        return self._jwks_client

    def verify_token(self, token: str) -> dict:
        """Verify a Supabase JWT token and return the payload."""
        jwks_client = self._get_jwks_client()

        # Get signing key - this may trigger JWKS refresh on key rotation
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as e:
            raise jwt.InvalidTokenError(f"Unable to find signing key: {e}")

        # Verify with explicit algorithm allowlist - never trust alg from token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=self.ALLOWED_ALGORITHMS,
            audience=self._settings.SUPABASE_AUDIENCE,
            issuer=self._settings.SUPABASE_ISSUER,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )
        return payload

    def get_user_id(self, token: str) -> str:
        """Extract and verify user ID from token."""
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")
        return user_id


# Global verifier instance
_jwt_verifier: "SupabaseJWTVerifier | None" = None


def get_jwt_verifier() -> "SupabaseJWTVerifier":
    """Get the global JWT verifier instance."""
    global _jwt_verifier
    if _jwt_verifier is None:
        _jwt_verifier = SupabaseJWTVerifier()
    return _jwt_verifier