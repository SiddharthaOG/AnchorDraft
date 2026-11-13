import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.middleware import RequestIdMiddleware


def make_request(request_id: str | None = None) -> Request:
    headers = []
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("ascii")))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/v1/health",
        "raw_path": b"/v1/health",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    })


@pytest.mark.asyncio
async def test_request_id_middleware_preserves_safe_correlation_id():
    middleware = RequestIdMiddleware(app=lambda *_: None)
    request = make_request("browser-request-123")

    async def call_next(current_request):
        assert current_request.state.request_id == "browser-request-123"
        return Response("ok")

    response = await middleware.dispatch(request, call_next)
    assert response.headers["X-Request-Id"] == "browser-request-123"


@pytest.mark.asyncio
async def test_request_id_middleware_replaces_unbounded_correlation_id():
    middleware = RequestIdMiddleware(app=lambda *_: None)
    request = make_request("x" * 129)

    async def call_next(current_request):
        assert len(current_request.state.request_id) == 36
        return Response("ok")

    response = await middleware.dispatch(request, call_next)
    assert len(response.headers["X-Request-Id"]) == 36
    assert response.headers["X-Request-Id"] != "x" * 129
