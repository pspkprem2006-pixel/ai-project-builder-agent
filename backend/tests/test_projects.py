PROJECT_PAYLOAD = {
    "name": "Hospital Management System",
    "description": "Manage patients, appointments, records and billing.",
    "category": "Healthcare",
    "target_users": "Admins, doctors, receptionists",
    "features": ["Patient registration", "Appointments", "Medical records", "Billing"],
    "preferred_frontend": "Next.js",
    "preferred_backend": "FastAPI",
    "database": "PostgreSQL",
    "auth_method": "JWT",
    "deployment_platform": "Docker",
    "language": "TypeScript",
}


def test_create_project(client, auth_headers):
    resp = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == PROJECT_PAYLOAD["name"]
    assert body["status"] == "draft"
    assert body["blueprint"] is None


def test_list_projects_and_search(client, auth_headers):
    client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers)
    resp = client.get("/api/v1/projects", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["items"][0]["name"] == PROJECT_PAYLOAD["name"]

    resp = client.get("/api/v1/projects?q=Hospital", headers=auth_headers)
    assert resp.json()["total"] >= 1
    resp = client.get("/api/v1/projects?q=zzz-not-found", headers=auth_headers)
    assert resp.json()["total"] == 0


def test_get_update_delete_project(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]

    resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200

    resp = client.put(
        f"/api/v1/projects/{project_id}", json={"name": "Renamed", "features": ["A", "B"]}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["features"] == ["A", "B"]

    assert client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).status_code == 404


def test_project_isolation_between_users(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "password123", "full_name": "Other"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/v1/projects/{project_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}", headers=other_headers).status_code == 404


def test_statistics(client, auth_headers):
    client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers)
    resp = client.get("/api/v1/projects/statistics", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_projects"] >= 1
    assert body["by_category"]["Healthcare"] >= 1


def test_duplicate_project(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/duplicate", headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Hospital Management System (copy)"


def test_templates_endpoint(client, auth_headers):
    resp = client.get("/api/v1/projects/templates", headers=auth_headers)
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) >= 6
    assert any(t["category"] == "Healthcare" for t in templates)


def test_suggestions_endpoint(client, auth_headers):
    resp = client.get("/api/v1/projects/suggestions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
