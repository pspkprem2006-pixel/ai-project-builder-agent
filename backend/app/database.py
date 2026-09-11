from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

DB_URL = settings.DATABASE_URL
if DB_URL.startswith("sqlite"):
    db_path = DB_URL.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if db_path == ":memory:":
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            DB_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import (  # noqa: F401
        action_result,
        blueprint_revision,
        generation_job,
        project,
        rate_limit,
        user,
    )

    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """Idempotent additive migrations for databases created before Phase 9.

    ``create_all`` never alters existing tables, so new columns and indexes are
    added explicitly. Every statement is guarded: the column/index already
    exists after the first successful run.
    """
    from sqlalchemy import text

    statements = [
        "ALTER TABLE generation_jobs ADD COLUMN action_id VARCHAR(64)",
        "ALTER TABLE generation_jobs ADD COLUMN action_input TEXT",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_generation_jobs_active_action "
            "ON generation_jobs (project_id, action_id) "
            "WHERE status IN ('queued', 'running') AND action_id IS NOT NULL"
        ),
        "ALTER TABLE action_results ADD COLUMN quality VARCHAR(16)",
        "ALTER TABLE action_results ADD COLUMN completeness INTEGER",
        "ALTER TABLE action_results ADD COLUMN consistency_status VARCHAR(16)",
        "ALTER TABLE action_results ADD COLUMN artifact_available BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE action_results ADD COLUMN applied_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
        (
            "ALTER TABLE blueprint_revisions ADD COLUMN applied_by "
            "INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ),
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_blueprint_revisions_project_rev "
            "ON blueprint_revisions (project_id, revision)"
        ),
        "CREATE TABLE IF NOT EXISTS action_results ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,"
        "  action_id VARCHAR(64) NOT NULL,"
        "  status VARCHAR(20) NOT NULL,"
        "  input TEXT,"
        "  result TEXT,"
        "  section VARCHAR(64),"
        "  warnings TEXT,"
        "  provider VARCHAR(32),"
        "  blueprint_revision INTEGER NOT NULL DEFAULT 0,"
        "  quality VARCHAR(16),"
        "  completeness INTEGER,"
        "  consistency_status VARCHAR(16),"
        "  artifact_available BOOLEAN NOT NULL DEFAULT 0,"
        "  applied BOOLEAN NOT NULL DEFAULT 0,"
        "  applied_at DATETIME,"
        "  applied_by INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        "  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "  completed_at DATETIME"
        ")",
        "CREATE INDEX IF NOT EXISTS ix_action_results_project_created "
        "ON action_results (project_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_action_results_action_created "
        "ON action_results (action_id, created_at)",
        "CREATE TABLE IF NOT EXISTS blueprint_revisions ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,"
        "  revision INTEGER NOT NULL,"
        "  section VARCHAR(64) NOT NULL,"
        "  source_action VARCHAR(64) NOT NULL,"
        "  action_result_id INTEGER,"
        "  previous_section TEXT,"
        "  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")",
        "CREATE INDEX IF NOT EXISTS ix_blueprint_revisions_project_rev "
        "ON blueprint_revisions (project_id, revision)",
        "CREATE INDEX IF NOT EXISTS ix_blueprint_revisions_created "
        "ON blueprint_revisions (project_id, created_at)",
    ]
    for statement in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception:  # noqa: BLE001 - additive migration; already applied is fine
            pass
