"""Deterministic artifact generation for the AI Action Engine.

``generate-ci-cd`` and ``generate-test-strategy`` can produce downloadable
artifacts (GitHub Actions workflows, test scaffolding) when the blueprint
stack contains enough information. Generation is fully deterministic — no
LLM involved — and reuses the hardened ZIP pipeline (``codegen.base``) so
entry paths are validated before archiving.

Security rules enforced here:
- Never emit API keys, passwords, tokens or credentials — CI files reference
  secret stores only (``${{ secrets.* }}`` placeholders).
- Only generate files when the detected stack actually supports them.
- Every artifact is labelled "Generated test scaffolding" / "generated CI/CD
  configuration" so users never mistake it for a complete solution.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.codegen.base import safe_zip_path

#: Actions that are allowed to produce downloadable artifacts.
ARTIFACT_ACTIONS: dict[str, str] = {
    "generate-ci-cd": "ci-cd",
    "generate-test-strategy": "test-scaffold",
}

#: Patterns for literal secret VALUES (assignments, real token formats).
#: Placeholder references like ``${{ secrets.DEPLOY_TOKEN }}`` are fine and
#: must not trip the check — only an actual embedded value is rejected.
_SECRET_VALUE_PATTERNS = (
    r"(?i)(api[_-]?key|secret[_-]?key|password|private[_-]?key|token|credential|bearer)\s*[=:]\s*['\"][A-Za-z0-9+/_\-\.]{8,}['\"]",
    r"sk-[A-Za-z0-9]{16,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"Bearer\s+[A-Za-z0-9._\-]{20,}",
)


def _contains_secret(value: str) -> bool:
    return any(re.search(pattern, value) for pattern in _SECRET_VALUE_PATTERNS)


def _safe_text(value: Any, max_len: int = 400) -> str:
    text = str(value or "").strip()
    return text[:max_len]


def _stack(project: Any, blueprint: dict[str, Any]) -> dict[str, str]:
    """Detect the project stack from project fields and blueprint metadata."""
    technology = blueprint.get("technology_selection") or {}
    stack = {}
    for key in ("frontend", "backend", "database", "deployment"):
        stack[key] = (
            _safe_text(getattr(project, f"preferred_{key}", None) or getattr(project, key, None))
            or ""
        ).lower()
    selected = technology.get("selected_stack") or []
    if isinstance(selected, list):
        for entry in selected:
            if not isinstance(entry, dict):
                continue
            layer = str(entry.get("layer") or "").lower()
            tech = str(entry.get("technology") or "").lower()
            if layer == "frontend" and not stack["frontend"]:
                stack["frontend"] = tech
            elif layer == "backend" and not stack["backend"]:
                stack["backend"] = tech
            elif layer == "database" and not stack["database"]:
                stack["database"] = tech
            elif layer == "deployment" and not stack["deployment"]:
                stack["deployment"] = tech
    return stack


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "app"


# ---------------------------------------------------------------------------
# CI/CD artifacts (Part 14)
# ---------------------------------------------------------------------------


def _backend_install(backend: str) -> tuple[str, str, str]:
    """Return (install, lint, test) commands for the detected backend."""
    if "node" in backend or "express" in backend or "nest" in backend:
        return "npm ci", "npm run lint", "npm test"
    if "java" in backend or "spring" in backend:
        return "./mvnw install -DskipTests", "./mvnw verify -DskipTests", "./mvnw test"
    if "go" in backend:
        return "go mod download", "go vet ./...", "go test ./..."
    # Default to Python (FastAPI, Django, Flask)
    return "pip install -r requirements.txt", "ruff check .", "pytest -q"


def _frontend_install(frontend: str) -> tuple[str, str, str]:
    if "next" in frontend or "react" in frontend or "vue" in frontend:
        return "npm ci", "npm run lint", "npm run test"
    return "", "", ""


def build_ci_cd_artifact(project: Any, blueprint: dict[str, Any]) -> dict[str, str] | None:
    """Build a GitHub Actions workflow artifact for the detected stack.

    Returns a mapping of safe ZIP entry paths to file contents, or ``None``
    when the stack does not contain enough information.
    """
    stack = _stack(project, blueprint)
    backend = stack.get("backend") or ""
    frontend = stack.get("frontend") or ""
    database = stack.get("database") or ""
    deployment = stack.get("deployment") or ""

    if not backend and not frontend:
        return None

    install, lint, test = _backend_install(backend)
    f_install, f_lint, f_test = _frontend_install(frontend)

    steps = [
        "actions/checkout@v4",
    ]
    if frontend and (f_install or f_lint or f_test):
        steps.append("actions/setup-node@v4  # with: node-version: 20, cache: npm")
        steps.append(f"npm ci --prefix frontend  # {f_install or 'install frontend deps'}")
        if f_lint:
            steps.append(f"npm run lint --prefix frontend  # {f_lint}")
        if f_test:
            steps.append(f"npm run test --prefix frontend  # {f_test}")
    if backend:
        if "node" in backend:
            steps.append("actions/setup-node@v4  # with: node-version: 20, cache: npm")
        elif "java" in backend:
            steps.append("actions/setup-java@v4  # with: distribution: temurin, java-version: 21")
        elif "go" in backend:
            steps.append("actions/setup-go@v5  # with: go-version-file: go.mod")
        else:
            steps.append("actions/setup-python@v5  # with: python-version: '3.12'")
        steps.append(f"{install}  # install backend dependencies")
        if lint:
            steps.append(f"{lint}  # lint")
        if test:
            steps.append(f"{test}  # unit/integration tests")

    ci_yml = f"""# Generated CI/CD configuration for {_safe_text(project.name, 120)}.
# Deterministically derived from the blueprint stack; adjust before use.
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
""" + "\n".join(f"      - uses: {step}" for step in steps) + """
      - name: Security scan (dependency check)
        run: echo "Run your SAST/dependency scanner here (e.g. pip-audit, npm audit, trivy)."

  # NOTE: secrets are referenced from the repository secret store only.
  # Never commit real credentials.
"""

    files: dict[str, str] = {".github/workflows/ci.yml": ci_yml}

    if deployment:
        deploy_yml = f"""# Generated deployment workflow for {_safe_text(project.name, 120)}.
# Template only — deployment details must be confirmed by the team.
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build artifact
        run: echo "Build the {_safe_text(backend or 'application', 80)} artifact here."
      - name: Deploy to {_safe_text(deployment, 80)}
        run: echo "Deploy via {_safe_text(deployment, 80)} using ${{{{ secrets.DEPLOY_TOKEN }}}}."
      - name: Smoke test
        run: echo "Run a post-deploy smoke test against the {_safe_text(database or 'database', 80)}."
"""
        files[".github/workflows/deploy.yml"] = deploy_yml

    if database:
        files["README-ARTIFACT.md"] = (
            "Generated CI/CD configuration (scaffolding, not a complete pipeline).\n"
            f"Detected stack: backend={backend or 'unknown'}, frontend={frontend or 'unknown'}, "
            f"database={database or 'unknown'}, deployment={deployment or 'unknown'}.\n"
            "No secrets were included; reference repository secret stores instead.\n"
        )

    # Hard safety net: never ship a file that could embed a secret literal.
    for path in list(files):
        safe_zip_path(path)
        if _contains_secret(files[path]):
            return None
    return files


# ---------------------------------------------------------------------------
# Test scaffolding artifacts (Part 15)
# ---------------------------------------------------------------------------


def build_test_scaffold(project: Any, blueprint: dict[str, Any]) -> dict[str, str] | None:
    """Build stack-appropriate test scaffolding files.

    Returns a mapping of safe ZIP entry paths to file contents, or ``None``
    when the stack does not contain enough information. Files are labelled as
    "Generated test scaffolding" and are not a complete test suite.
    """
    stack = _stack(project, blueprint)
    backend = stack.get("backend") or ""
    frontend = stack.get("frontend") or ""
    database = stack.get("database") or ""
    api = blueprint.get("api") or {}
    endpoints = [e for e in (api.get("endpoints") or []) if isinstance(e, dict) and e.get("path")]

    if not backend and not frontend:
        return None

    slug = _slug(project.name or "app")
    files: dict[str, str] = {}
    label = "Generated test scaffolding — NOT a complete test suite."

    python_like = not backend or any(
        marker in backend for marker in ("python", "fastapi", "django", "flask")
    )
    if python_like:
        sample_endpoint = endpoints[0].get("path", "/api/v1/items") if endpoints else "/api/v1/items"
        files["tests/conftest.py"] = f'''"""Shared pytest fixtures ({label})"""

import pytest


@pytest.fixture()
def client():
    """Test client for the {_safe_text(project.name, 80)} API."""
    # Point at the application's test client / in-memory database.
    raise NotImplementedError("Wire this to your framework's test client.")


@pytest.fixture()
def sample_payload():
    return {{"name": "sample"}}
'''
        files["tests/test_api_smoke.py"] = f'''"""API smoke tests ({label})"""


def test_health_endpoint(client):
    """The sample endpoint responds with 200."""
    # Replace with a real endpoint path from the blueprint.
    assert client is not None
    # response = client.get("{sample_endpoint}")
    # assert response.status_code == 200
'''
        if database:
            files["tests/test_database.py"] = f'''"""Database integrity tests ({label})"""


def test_schema_constraints():
    """Constraint checks for the {_safe_text(database, 40)} schema."""
    # Add assertions for unique indexes / foreign keys from the blueprint.
    assert True
'''
        files["pytest.ini"] = "[pytest]\ntestpaths = tests\naddopts = -q\n"
    elif "node" in backend or "express" in backend or "nest" in backend:
        files["tests/api.test.js"] = f'''// {label}
// Smoke tests for the {_safe_text(project.name, 80)} API.

const request = require("supertest");

describe("API smoke", () => {{
  it("responds on the health endpoint", async () => {{
    // const res = await request(app).get("/health");
    // expect(res.statusCode).toBe(200);
    expect(true).toBe(true);
  }});
}});
'''
        files["package.json"] = (
            '{\n  "name": "' + slug + '-tests",\n  "private": true,\n'
            '  "scripts": { "test": "jest" },\n'
            '  "devDependencies": { "jest": "^29.0.0", "supertest": "^7.0.0" }\n}\n'
        )
    elif "java" in backend or "spring" in backend:
        files["src/test/java/com/example/AppSmokeTest.java"] = f'''package com.example;

// {label}
import org.junit.jupiter.api.Test;

class AppSmokeTest {{

    @Test
    void contextLoads() {{
        // Wire this to a Spring Boot @SpringBootTest for the real suite.
    }}
}}
'''
    if frontend and ("react" in frontend or "next" in frontend or "vue" in frontend):
        files["frontend/src/__tests__/smoke.test.ts"] = f'''// {label}
// Frontend smoke test for the {_safe_text(project.name, 80)} UI.
import {{ describe, expect, it }} from "vitest";

describe("UI smoke", () => {{
  it("renders without crashing", () => {{
    expect(true).toBe(true);
  }});
}});
'''
        files["frontend/README-TESTS.md"] = (
            f"{label}\nRun with your framework's runner (Vitest/Jest). "
            "Replace placeholder assertions with real component tests.\n"
        )

    files["README-ARTIFACT.md"] = (
        f"{label}\n"
        f"Detected stack: backend={backend or 'unknown'}, frontend={frontend or 'unknown'}, "
        f"database={database or 'unknown'}.\n"
        "No secrets were included.\n"
    )

    for path in list(files):
        safe_zip_path(path)
        if _contains_secret(files[path]):
            return None
    return files
