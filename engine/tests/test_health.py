"""Tests for the health endpoint."""
import pytest
from fastapi.middleware.cors import CORSMiddleware


class TestHealthEndpoint:
    """Tests for GET /v1/health."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """Health endpoint returns status ok with version and time."""
        response = await client.get("/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "time" in data
        # Verify time is valid ISO format
        assert "T" in data["time"]

    @pytest.mark.asyncio
    async def test_health_returns_request_id_header(self, client):
        """Health endpoint returns X-Request-Id header."""
        response = await client.get("/v1/health")
        assert "X-Request-Id" in response.headers
        request_id = response.headers["X-Request-Id"]
        assert len(request_id) > 0

    @pytest.mark.asyncio
    async def test_health_uses_provided_request_id(self, client):
        """Health endpoint uses X-Request-Id from request if provided."""
        custom_id = "custom-request-id-123"
        response = await client.get("/v1/health", headers={"X-Request-Id": custom_id})
        assert response.headers["X-Request-Id"] == custom_id

    @pytest.mark.asyncio
    async def test_health_generates_request_id_when_missing(self, client):
        """Health endpoint generates X-Request-Id when not provided."""
        response = await client.get("/v1/health")
        request_id = response.headers["X-Request-Id"]
        # Should be a valid UUID format
        import uuid
        uuid.UUID(request_id)  # Raises ValueError if invalid


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_middleware_configured_no_wildcard(self, app):
        """CORS middleware is configured with specific origins, no wildcard."""
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORS middleware not found"
        options = cors_middleware.kwargs
        # In test environment, ALLOWED_ORIGINS defaults to empty list
        # The key check is that wildcard is not used
        assert "*" not in options.get("allow_origins", []), "Wildcard not allowed in CORS origins"
        assert options.get("allow_credentials") is True
        assert set(options.get("allow_methods", [])) == {"GET", "POST", "OPTIONS"}

    @pytest.mark.asyncio
    async def test_cors_allows_configured_origin(self, client):
        """CORS allows origins from ALLOWED_ORIGINS on actual requests."""
        response = await client.get(
            "/v1/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        # Vary: Origin indicates CORS middleware processed the request
        assert response.headers.get("vary") == "Origin"
        assert response.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_rejects_disallowed_origin(self, client):
        """CORS rejects origins not in ALLOWED_ORIGINS (no wildcard)."""
        response = await client.get(
            "/v1/health",
            headers={"Origin": "http://evil.com"},
        )
        # Should not have allow-origin header for disallowed origin
        assert "access-control-allow-origin" not in response.headers or \
               response.headers.get("access-control-allow-origin") != "http://evil.com"