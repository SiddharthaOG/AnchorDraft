"""Tests for Supabase JWT verification with ES256 and RS256 support."""

import pytest
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec

from app.auth.jwt import SupabaseJWTVerifier


@pytest.fixture(autouse=True)
def isolate_test_config(monkeypatch):
    """Isolate test configuration by setting required env vars and clearing caches."""
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_ISSUER", "https://test.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_AUDIENCE", "authenticated")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    # Clear settings cache to ensure fresh config
    from app.core.config import clear_settings_cache
    clear_settings_cache()
    # Also clear the JWT verifier singleton
    import app.auth.jwt as jwt_module
    jwt_module._jwt_verifier = None
    yield
    # Cleanup after test
    from app.core.config import clear_settings_cache
    clear_settings_cache()


# Helper to create test RSA private/public key pair
def generate_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_key, public_key, private_pem, public_pem


# Helper to create test EC (P-256) private/public key pair
def generate_ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_key, public_key, private_pem, public_pem


def create_jwt_token(payload: dict, private_key, algorithm: str, key_id: str = "test-key") -> str:
    """Create a JWT token with the given payload and private key."""
    headers = {"kid": key_id}
    if algorithm == "RS256":
        headers["alg"] = "RS256"
    elif algorithm == "ES256":
        headers["alg"] = "ES256"

    token = jwt.encode(
        payload,
        private_key,
        algorithm=algorithm,
        headers=headers
    )
    return token


class TestSupabaseJWTVerifier:
    """Tests for SupabaseJWTVerifier algorithm support."""

    def setup_method(self):
        """Generate test keys before each test."""
        self.rsa_private, self.rsa_public, self.rsa_private_pem, self.rsa_public_pem = generate_rsa_keypair()
        self.ec_private, self.ec_public, self.ec_private_pem, self.ec_public_pem = generate_ec_keypair()

        # Create JWKS with both keys
        self.jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "rsa-test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": self._int_to_base64url(self.rsa_public.public_numbers().n),
                    "e": self._int_to_base64url(self.rsa_public.public_numbers().e),
                },
                {
                    "kty": "EC",
                    "kid": "ec-test-key",
                    "use": "sig",
                    "alg": "ES256",
                    "crv": "P-256",
                    "x": self._int_to_base64url(self.ec_public.public_numbers().x),
                    "y": self._int_to_base64url(self.ec_public.public_numbers().y),
                },
                {
                    "kty": "oct",
                    "kid": "hs256-test-key",
                    "use": "sig",
                    "alg": "HS256",
                    "k": "dGVzdC1zZWNyZXQta2V5LWZvci10ZXN0aW5nLWxvbmdlci10ZXN0LWtleQ==",  # base64url encoded "test-secret-key-for-testing-longer-test-key"
                }
            ]
        }

    def _int_to_base64url(self, value: int) -> str:
        """Convert integer to base64url encoding."""
        byte_length = (value.bit_length() + 7) // 8
        return jwt.utils.base64url_encode(value.to_bytes(byte_length, 'big')).decode('ascii')

    def create_mock_jwks_client(self, jwks):
        """Create a mock PyJWKClient that returns our test keys."""
        mock_client = MagicMock()

        def get_signing_key_from_jwt(token):
            # Parse token header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            key_data = next((k for k in self.jwks["keys"] if k["kid"] == kid), None)
            if not key_data:
                raise jwt.PyJWKClientError(f"Key not found for kid: {kid}")

            mock_key = MagicMock()
            kty = key_data.get("kty")
            if kty == "RSA":
                mock_key.key = self.rsa_public
            elif kty == "EC":
                mock_key.key = self.ec_public
            elif kty == "oct":
                # For oct (symmetric) keys, use the key material from JWKS
                # This allows the key lookup to succeed, then algorithm check will reject HS256
                k_b64 = key_data.get("k")
                if k_b64:
                    import base64
                    key_bytes = base64.urlsafe_b64decode(k_b64 + "==")
                    mock_key.key = key_bytes
                else:
                    raise jwt.PyJWKClientError(f"No key material for oct key: {kid}")
            else:
                raise jwt.PyJWKClientError(f"Unknown key type: {kty}")
            return mock_key

        mock_client.get_signing_key_from_jwt.side_effect = get_signing_key_from_jwt
        return mock_client

    def test_allowed_algorithms_includes_es256_and_rs256(self):
        """Verifier must allow both RS256 and ES256."""
        verifier = SupabaseJWTVerifier()
        assert "RS256" in verifier.ALLOWED_ALGORITHMS
        assert "ES256" in verifier.ALLOWED_ALGORITHMS
        assert len(verifier.ALLOWED_ALGORITHMS) == 2

    def test_valid_es256_token_succeeds(self):
        """Valid ES256 token with valid signature passes verification."""
        verifier = SupabaseJWTVerifier()

        # Create a valid ES256 token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()
            user_id = verifier.get_user_id(token)

            assert user_id == "test-user-id"

    def test_valid_rs256_token_succeeds(self):
        """Valid RS256 token with valid signature passes verification."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = create_jwt_token(payload, self.rsa_private, "RS256", "rsa-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()
            user_id = verifier.get_user_id(token)

            assert user_id == "test-user-id"

    def test_hs256_token_rejected(self):
        """HS256 token is rejected (not in allowlist)."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        # Create HS256 token (symmetric key) - use a key that's at least 32 bytes for HS256
        hs256_private = b"test-secret-key-for-jwt-algorithm-rejection-testing"
        token = jwt.encode(payload, hs256_private, algorithm="HS256", headers={"kid": "hs256-test-key"})

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(jwt.InvalidTokenError) as exc_info:
                verifier.get_user_id(token)

            # Should be rejected due to algorithm not allowed
            assert "Algorithm not allowed" in str(exc_info.value) or "not allowed" in str(exc_info.value).lower()

    def test_invalid_signature_rejected(self):
        """Token with invalid signature is rejected."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        # Create valid token
        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        # Tamper with the token (modify last byte)
        tampered_token = token[:-1] + ("a" if token[-1] != "a" else "b")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(jwt.InvalidTokenError):
                verifier.get_user_id(tampered_token)

    def test_incorrect_issuer_rejected(self):
        """Token with incorrect issuer is rejected."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://wrong.supabase.co/auth/v1",  # Wrong issuer
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(jwt.InvalidTokenError) as exc_info:
                verifier.get_user_id(token)

            assert "issuer" in str(exc_info.value).lower()

    def test_incorrect_audience_rejected(self):
        """Token with incorrect audience is rejected."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user-id",
            "aud": "wrong-audience",  # Wrong audience
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(jwt.InvalidTokenError) as exc_info:
                verifier.get_user_id(token)

            assert "audience" in str(exc_info.value).lower() or "aud" in str(exc_info.value).lower()

    def test_expired_token_rejected(self):
        """Expired token is rejected."""
        verifier = SupabaseJWTVerifier()

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        payload = {
            "sub": "test-user-id",
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int(past.timestamp()),  # Expired 2 hours ago
            "iat": int((past - timedelta(hours=1)).timestamp())
        }

        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(jwt.InvalidTokenError) as exc_info:
                verifier.get_user_id(token)

            assert "expired" in str(exc_info.value).lower() or "exp" in str(exc_info.value).lower()

    def test_missing_subject_claim_rejected(self):
        """Token missing subject claim is rejected."""
        verifier = SupabaseJWTVerifier()

        now = datetime.now(timezone.utc)
        payload = {
            # "sub" missing
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = create_jwt_token(payload, self.ec_private, "ES256", "ec-test-key")

        with patch('app.auth.jwt.PyJWKClient') as mock_jwks_client:
            mock_client = self.create_mock_jwks_client(self.jwks)
            mock_jwks_client.return_value = mock_client

            verifier = SupabaseJWTVerifier()

            with pytest.raises(ValueError) as exc_info:
                verifier.get_user_id(token)

            assert "subject" in str(exc_info.value).lower() or "sub" in str(exc_info.value).lower()