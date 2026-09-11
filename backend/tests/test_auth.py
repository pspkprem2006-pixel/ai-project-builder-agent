def test_register_success(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123", "full_name": "Jane Doe"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "new@example.com"
    assert body["token_type"] == "bearer"


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "password123", "full_name": "Dup"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_register_weak_password(client):
    resp = client.post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "short", "full_name": "W"}
    )
    assert resp.status_code == 422


def test_login_success(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "password123", "full_name": "Login"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "password123"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "bad@example.com", "password": "password123", "full_name": "Bad"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "bad@example.com", "password": "wrongpass1"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_me_and_profile_update(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert "@example.com" in resp.json()["email"]

    resp = client.put("/api/v1/auth/me", json={"full_name": "Updated Name"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


def test_forgot_password_dev_token(client, monkeypatch):
    import app.api.auth as auth_module

    monkeypatch.setattr(auth_module.settings, "DEBUG", True)
    client.post(
        "/api/v1/auth/register",
        json={"email": "reset@example.com", "password": "password123", "full_name": "Reset"},
    )
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert resp.status_code == 200
    assert resp.json()["reset_token"]


def test_forgot_password_unknown_email_is_safe(client):
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None


def test_reset_password_flow(client, monkeypatch):
    import app.api.auth as auth_module

    monkeypatch.setattr(auth_module.settings, "DEBUG", True)
    client.post(
        "/api/v1/auth/register",
        json={"email": "cycle@example.com", "password": "oldpassword1", "full_name": "Cycle"},
    )
    token = client.post("/api/v1/auth/forgot-password", json={"email": "cycle@example.com"}).json()["reset_token"]
    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword1"})
    assert resp.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "cycle@example.com", "password": "newpassword1"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "cycle@example.com", "password": "oldpassword1"}).status_code == 401


def test_reset_password_invalid_token(client):
    resp = client.post("/api/v1/auth/reset-password", json={"token": "bogus", "new_password": "newpassword1"})
    assert resp.status_code == 400
