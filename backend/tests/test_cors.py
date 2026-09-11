"""CORS middleware behavior: credentialed requests with explicit origins.

Production configuration is covered in test_config_security.py; these tests
verify the middleware itself (preflight echo, disallowed-origin rejection,
credentials handling) against the test-app CORS_ORIGINS=http://test.local.
"""


def test_preflight_from_allowed_origin_is_echoed(client):
    resp = client.options(
        "/api/v1/projects",
        headers={
            "Origin": "http://test.local",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://test.local"
    assert resp.headers.get("access-control-allow-credentials") == "true"
    assert "authorization" in resp.headers.get("access-control-allow-headers", "").lower()


def test_preflight_from_disallowed_origin_not_echoed(client):
    resp = client.options(
        "/api/v1/projects",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") is None


def test_simple_request_from_allowed_origin_echoed(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "cors@example.com", "password": "password123"},
        headers={"Origin": "http://test.local"},
    )
    assert resp.status_code in (401, 200)
    assert resp.headers.get("access-control-allow-origin") == "http://test.local"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_simple_request_from_disallowed_origin_not_echoed(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "cors@example.com", "password": "password123"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.headers.get("access-control-allow-origin") is None
