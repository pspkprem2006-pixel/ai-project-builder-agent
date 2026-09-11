"""Authentication & session security regression tests.

Covers token validation edge cases (expired / malformed / wrong signature /
missing / unknown subject / inactive user), the stateless logout contract,
and cross-user authorization on every project-scoped resource.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.security import create_access_token
from app.database import SessionLocal
from app.models.user import User
from tests.test_projects import PROJECT_PAYLOAD


def _register(client, prefix: str) -> dict:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Security Test"},
    )
    assert resp.status_code == 201, resp.text
    return {"email": email, "token": resp.json()["access_token"], "id": resp.json()["user"]["id"]}


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


def test_me_with_valid_token(client):
    account = _register(client, "valid")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {account['token']}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == account["email"]


def test_me_with_expired_token(client):
    account = _register(client, "expired")
    expired = create_access_token(account["id"], expires_minutes=-5)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_me_with_malformed_token(client):
    for bad in ("not-a-jwt", "abc.def", "a.b.c.d.e", ""):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert resp.status_code == 401, f"token {bad!r} should be rejected"


def test_me_with_wrong_signature(client):
    account = _register(client, "sig")
    payload = {"sub": str(account["id"]), "exp": datetime.now(UTC) + timedelta(hours=1), "iat": datetime.now(UTC)}
    forged = jwt.encode(payload, "attacker-secret-key", algorithm="HS256")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_me_without_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects").status_code == 401


def test_me_token_for_unknown_user(client):
    token = create_access_token(999_999_999)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_me_token_for_inactive_user(client):
    account = _register(client, "inactive")
    with SessionLocal() as db:
        user = db.get(User, account["id"])
        user.is_active = False
        db.commit()
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {account['token']}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout (stateless JWT contract)
# ---------------------------------------------------------------------------


def test_logout_endpoint_and_stateless_session(client, auth_headers):
    resp = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert resp.status_code == 204
    # Session ends client-side: a request without the token is rejected.
    assert client.get("/api/v1/projects").status_code == 401


# ---------------------------------------------------------------------------
# Authorization (cross-user access must be denied with 404)
# ---------------------------------------------------------------------------


def _create_owner_project(client, owner_headers) -> int:
    resp = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=owner_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_other_user_cannot_access_project_resources(client):
    owner = _register(client, "owner")
    intruder = _register(client, "intruder")
    owner_headers = {"Authorization": f"Bearer {owner['token']}"}
    intruder_headers = {"Authorization": f"Bearer {intruder['token']}"}

    project_id = _create_owner_project(client, owner_headers)

    # Owner can read their own project (sanity).
    assert client.get(f"/api/v1/projects/{project_id}", headers=owner_headers).status_code == 200

    resource_requests = [
        ("GET", f"/api/v1/projects/{project_id}"),
        ("PUT", f"/api/v1/projects/{project_id}"),
        ("DELETE", f"/api/v1/projects/{project_id}"),
        ("POST", f"/api/v1/projects/{project_id}/duplicate"),
        ("POST", f"/api/v1/projects/{project_id}/generate"),
        ("GET", f"/api/v1/projects/{project_id}/export"),
        ("GET", f"/api/v1/projects/{project_id}/codegen/generators"),
        ("GET", f"/api/v1/projects/{project_id}/diagrams"),
        ("GET", f"/api/v1/projects/{project_id}/pm"),
        ("GET", f"/api/v1/projects/{project_id}/workspace/artifacts"),
    ]
    for method, path in resource_requests:
        kwargs = {"headers": intruder_headers}
        if method == "PUT":
            kwargs["json"] = {"name": "Renamed by intruder"}
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 404, f"{method} {path} should be 404 for a foreign user, got {resp.status_code}"
        # Never leak the resource's existence: the owner's request must be
        # authorized (a 404 is only legitimate for sub-resources that do not
        # exist yet, e.g. artifacts before a blueprint is generated).
        owner_kwargs = {"headers": owner_headers}
        if method == "PUT":
            owner_kwargs["json"] = {"name": "Renamed by owner"}
        owner_resp = client.request(method, path, **owner_kwargs)
        assert owner_resp.status_code not in (401, 403), (
            f"{method} {path} should be authorized for the owner, got {owner_resp.status_code}"
        )


def test_projects_list_is_scoped_to_owner(client):
    owner = _register(client, "list-owner")
    intruder = _register(client, "list-intruder")
    owner_headers = {"Authorization": f"Bearer {owner['token']}"}
    intruder_headers = {"Authorization": f"Bearer {intruder['token']}"}

    _create_owner_project(client, owner_headers)
    resp = client.get("/api/v1/projects", headers=intruder_headers)
    assert resp.status_code == 200
    assert all(item["user_id"] == intruder["id"] for item in resp.json()["items"])


def test_statistics_and_suggestions_are_user_scoped(client):
    owner = _register(client, "stat-owner")
    intruder = _register(client, "stat-intruder")
    owner_headers = {"Authorization": f"Bearer {owner['token']}"}
    intruder_headers = {"Authorization": f"Bearer {intruder['token']}"}

    _create_owner_project(client, owner_headers)
    stats = client.get("/api/v1/projects/statistics", headers=intruder_headers).json()
    assert stats["total_projects"] == 0
    assert client.get("/api/v1/projects/suggestions", headers=intruder_headers).status_code == 200
