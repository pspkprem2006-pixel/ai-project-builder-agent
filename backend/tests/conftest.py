import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["OPENAI_API_KEY"] = ""
# Pin production-like mode so local backend/.env (DEBUG=true) never bleeds
# into the test suite; env vars take precedence over the dotenv file.
os.environ["DEBUG"] = "false"
# Explicit production-style CORS origin (the dev localhost default is refused
# when DEBUG=false).
os.environ["CORS_ORIGINS"] = "http://test.local"
# Generous auth rate limits so suite-wide flows are never throttled. The
# rate-limit regression tests override these per-test with tiny values.
os.environ["RATE_LIMIT_LOGIN"] = "100000"
os.environ["RATE_LIMIT_REGISTER"] = "100000"
os.environ["RATE_LIMIT_FORGOT"] = "100000"
os.environ["RATE_LIMIT_FORGOT_IP"] = "100000"
os.environ["RATE_LIMIT_RESET"] = "100000"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    import uuid

    email = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def drain_jobs():
    """Run all queued generation jobs synchronously (a test-local worker).

    Generation is durable in this application: ``POST /projects/{id}/generate``
    only creates a queued ``GenerationJob``. Tests that expect a finished
    blueprint call this after posting to simulate the worker.
    """

    def _drain(worker_id: str = "test-worker") -> list[str]:
        from app.database import SessionLocal
        from app.services.generation_jobs import claim_job, execute_job

        outcomes = []
        with SessionLocal() as db:
            while True:
                job_id = claim_job(db, worker_id)
                if job_id is None:
                    break
                outcomes.append(execute_job(job_id, worker_id))
        return outcomes

    return _drain
