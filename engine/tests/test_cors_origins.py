"""CORS policy tests for the review engine."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient


PREVIEW_ORIGIN_PATTERN = r"^https://anchordraft(?:-[a-z0-9-]+)?-siddharthaog\.vercel\.app$"


def make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://anchordraft.vercel.app"],
        allow_origin_regex=PREVIEW_ORIGIN_PATTERN,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["X-Request-Id", "Authorization", "Content-Type"],
    )
    @app.post("/v1/reviews")
    async def start_review():
        return {"ok": True}

    @app.patch("/v1/kits/{kit_id}/name")
    async def rename_kit(kit_id: str):
        return {"kit_id": kit_id, "name": "Renamed"}

    return TestClient(app)


def test_allows_stable_branch_preview_origin_preflight():
    response = make_client().options(
        "/v1/reviews",
        headers={
            "Origin": "https://anchordraft-git-feat-visual-brand-compliance-siddharthaog.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://anchordraft-git-feat-visual-brand-compliance-siddharthaog.vercel.app"


def test_allows_immutable_preview_deployment_origin_preflight():
    response = make_client().options(
        "/v1/reviews",
        headers={
            "Origin": "https://anchordraft-7f2jlneiq-siddharthaog.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200


def test_rejects_unrelated_vercel_project_origin():
    response = make_client().options(
        "/v1/reviews",
        headers={
            "Origin": "https://malicious-project-siddharthaog.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 400



def test_allows_patch_preflight_for_kit_name_update():
    response = make_client().options(
        "/v1/kits/kit-draft-1/name",
        headers={
            "Origin": "https://anchordraft-git-polish-siddharthaog.vercel.app",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://anchordraft-git-polish-siddharthaog.vercel.app"
    assert "PATCH" in response.headers["access-control-allow-methods"]
