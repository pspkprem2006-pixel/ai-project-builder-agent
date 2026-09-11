"""Error handling: production responses never leak internals.

Unexpected exceptions become a generic 500 with server-side logging; expected
validation errors stay detailed; known failure modes stay 400/404.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import unhandled_exception_handler


def _make_boom_app() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail C:\\app\\secrets\\env")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_generic_500():
    with _make_boom_app() as client:
        resp = client.get("/boom")
        assert resp.status_code == 500
        body = resp.json()
        assert body == {"detail": "Internal Server Error"}
        assert "Traceback" not in resp.text
        assert "secret internal detail" not in resp.text
        assert "app" not in resp.text.lower() or "Internal Server Error" in resp.text


def test_unhandled_exception_logged_server_side(caplog):
    import logging

    caplog.set_level(logging.ERROR)
    with _make_boom_app() as client:
        client.get("/boom")
    assert any("Unhandled exception" in record.getMessage() for record in caplog.records)
    assert any("secret internal detail" in (record.exc_text or "") for record in caplog.records)


def test_404_and_400_messages_are_safe_and_expected(client):
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert "Traceback" not in resp.text
    resp = client.get("/api/v1/projects/1/export?format=evil")
    assert resp.status_code in (401, 400)
    assert "Traceback" not in resp.text


def test_unknown_generator_error_is_expected_404(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/nope", headers=headers)
    assert resp.status_code == 404
    assert "Unknown generator" in resp.json()["detail"]


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post(
        "/api/v1/projects", json={"name": "X", "description": "d"}, headers=auth_headers
    ).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    return project_id, auth_headers


def test_validation_errors_remain_detailed(client):
    resp = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "short"})
    assert resp.status_code == 422
    assert "Traceback" not in resp.text
