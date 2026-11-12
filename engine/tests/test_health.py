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
        assert set(options.get("allow_methods", [])) == {"GET", "POST", "PUT", "OPTIONS"}
        # Check allowed headers include X-Request-Id, Authorization, Content-Type
        assert "X-Request-Id" in options.get("allow_headers", [])
        assert "Authorization" in options.get("allow_headers", [])
        assert "Content-Type" in options.get("allow_headers", [])
        # Check expose_headers includes X-Request-Id
        assert "X-Request-Id" in options.get("expose_headers", [])

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

    @pytest.mark.asyncio
    async def test_cors_preflight_allowed_origin_with_x_request_id(self, client_comma_separated):
        """CORS preflight with allowed origin and X-Request-Id header is accepted."""
        response = await client_comma_separated.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-request-id",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert response.headers.get("access-control-allow-credentials") == "true"
        # Should allow the requested headers
        assert "x-request-id" in response.headers.get("access-control-allow-headers", "").lower()

    @pytest.mark.asyncio
    async def test_cors_preflight_put_is_allowed_for_visual_guideline_updates(self, client_comma_separated):
        response = await client_comma_separated.options(
            "/v1/kits/11111111-1111-1111-1111-111111111111/visual-guidelines",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert "put" in response.headers.get("access-control-allow-methods", "").lower()
        allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allowed_headers
        assert "content-type" in allowed_headers
        assert "x-request-id" in allowed_headers

    @pytest.mark.asyncio
    async def test_cors_preflight_disallowed_origin_rejected(self, client):
        """CORS preflight from disallowed origin is rejected."""
        response = await client.options(
            "/v1/health",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-request-id",
            },
        )
        # Should not allow the disallowed origin
        assert response.headers.get("access-control-allow-origin") != "http://evil.com"
        # May not have the header at all, or may be a different value
        # but definitely not the evil.com origin


class TestCORSCommaSeparated:
    """Tests for CORS configuration with comma-separated ALLOWED_ORIGINS."""

    def test_cors_middleware_configured_with_comma_separated(self, app_comma_separated):
        """CORS middleware is configured with comma-separated origins."""
        cors_middleware = None
        for middleware in app_comma_separated.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORS middleware not found"
        options = cors_middleware.kwargs
        assert options.get("allow_origins") == ["http://localhost:5173", "http://localhost:3000"]
        assert "*" not in options.get("allow_origins", []), "Wildcard not allowed in CORS origins"

    @pytest.mark.asyncio
    async def test_cors_allows_configured_origin(self, client_comma_separated):
        """CORS allows origins from comma-separated ALLOWED_ORIGINS on actual requests."""
        response = await client_comma_separated.get(
            "/v1/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        assert response.headers.get("vary") == "Origin"
        assert response.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_rejects_disallowed_origin(self, client_comma_separated):
        """CORS rejects origins not in comma-separated ALLOWED_ORIGINS (no wildcard)."""
        response = await client_comma_separated.get(
            "/v1/health",
            headers={"Origin": "http://evil.com"},
        )
        assert "access-control-allow-origin" not in response.headers or \
               response.headers.get("access-control-allow-origin") != "http://evil.com"

    @pytest.mark.asyncio
    async def test_cors_preflight_allowed_origin_with_x_request_id(self, client_comma_separated):
        """CORS preflight with allowed origin and X-Request-Id header is accepted."""
        response = await client_comma_separated.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-request-id",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert response.headers.get("access-control-allow-credentials") == "true"
        assert "x-request-id" in response.headers.get("access-control-allow-headers", "").lower()

    @pytest.mark.asyncio
    async def test_cors_preflight_disallowed_origin_rejected(self, client_comma_separated):
        """CORS preflight from disallowed origin is rejected."""
        response = await client_comma_separated.options(
            "/v1/health",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-request-id",
            },
        )
        assert response.headers.get("access-control-allow-origin") != "http://evil.com"

class TestIntegratedRouterRegistration:
    """Regression coverage for routers combined across the feature branches."""

    def test_confidentiality_policy_routes_registered(self, app):
        paths = app.openapi()["paths"]
        assert "/v1/organizations/me/confidentiality-policy" in paths
        assert "get" in paths["/v1/organizations/me/confidentiality-policy"]
        assert "put" in paths["/v1/organizations/me/confidentiality-policy"]

    def test_visual_guidelines_route_registered(self, app):
        paths = app.openapi()["paths"]
        assert "/v1/kits/{kit_id}/visual-guidelines" in paths
        assert "put" in paths["/v1/kits/{kit_id}/visual-guidelines"]

    @pytest.mark.asyncio
    async def test_cors_preflight_allows_visual_guideline_put(self, client_comma_separated):
        response = await client.options(
            "/v1/kits/22222222-2222-2222-2222-222222222222/visual-guidelines",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert "PUT" in response.headers.get("access-control-allow-methods", "")
