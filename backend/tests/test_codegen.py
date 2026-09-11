import io
import zipfile

import pytest

from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_list_generators(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/generators", headers=headers)
    assert resp.status_code == 200
    ids = [generator["id"] for generator in resp.json()]
    assert {"sql", "prisma", "sqlalchemy", "fastapi", "express", "spring", "react", "nextjs"} <= set(ids)


def test_generators_require_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/fastapi", headers=auth_headers)
    assert resp.status_code == 400


def test_unknown_generator(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/nope", headers=headers)
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "generator_id,expected_file",
    [
        ("sql", "schema.sql"),
        ("prisma", "prisma/schema.prisma"),
        ("sqlalchemy", "app/models.py"),
        ("fastapi", "app/main.py"),
        ("express", "src/app.js"),
        ("spring", "pom.xml"),
        ("react", "src/App.jsx"),
        ("nextjs", "src/lib/api.js"),
    ],
)
def test_download_zip(client, generated_project, generator_id, expected_file):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/{generator_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.content[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
        assert expected_file in names
        assert "README.md" in names


def test_manifest(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/fastapi/manifest", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["generator"] == "fastapi"
    assert body["total_bytes"] > 0
    assert any(f["path"] == "app/main.py" for f in body["files"])
