import asyncio
import json

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.errors import (
    generic_exception_handler,
    http_exception_handler,
    request_validation_exception_handler,
)


def make_request() -> Request:
    request = Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/v1/reviews/confirm",
        "raw_path": b"/v1/reviews/confirm",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    })
    request.state.request_id = "req-test-123"
    return request


def response_payload(response):
    return json.loads(response.body)


def test_http_exception_uses_standard_error_envelope_and_preserves_headers():
    response = http_exception_handler(
        make_request(),
        HTTPException(
            status_code=403,
            detail={"error": {"code": "forbidden", "message": "Not allowed"}},
            headers={"WWW-Authenticate": "Bearer"},
        ),
    )

    payload = response_payload(response)
    assert response.status_code == 403
    assert response.headers["www-authenticate"] == "Bearer"
    assert payload["error"]["code"] == "forbidden"
    assert payload["error"]["message"] == "Not allowed"
    assert payload["error"]["request_id"] == "req-test-123"


def test_http_exception_normalizes_string_detail():
    response = http_exception_handler(
        make_request(),
        HTTPException(status_code=409, detail="This preview has already been consumed"),
    )

    payload = response_payload(response)
    assert response.status_code == 409
    assert payload["error"]["code"] == "conflict"
    assert payload["error"]["message"] == "This preview has already been consumed"


def test_request_validation_error_does_not_echo_submitted_values():
    response = asyncio.run(request_validation_exception_handler(
        make_request(),
        RequestValidationError([{
            "type": "missing",
            "loc": ("body", "revision_id"),
            "msg": "Field required",
            "input": "private-submitted-value",
        }]),
    ))

    payload = response_payload(response)
    assert response.status_code == 422
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["reason"] == "request_validation_error"
    assert "revision_id: Field required" in payload["error"]["message"]
    assert "private-submitted-value" not in response.body.decode()
    assert payload["error"]["request_id"] == "req-test-123"


@pytest.mark.asyncio
async def test_generic_error_is_redacted_and_returns_request_id_header(caplog):
    private_detail = "private draft fragment must not be logged"
    response = await generic_exception_handler(
        make_request(),
        RuntimeError(private_detail),
    )

    payload = response_payload(response)
    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "req-test-123"
    assert payload["error"]["request_id"] == "req-test-123"
    assert payload["error"]["message"] == "Internal server error"
    assert private_detail not in response.body.decode()
    assert private_detail not in caplog.text
