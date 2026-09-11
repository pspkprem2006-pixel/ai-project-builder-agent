"""Database generators: raw SQL, Prisma schema, SQLAlchemy models."""

from __future__ import annotations

import re
from typing import Any

from app.services.codegen.base import (
    PRISMA_TYPE_MAP,
    SA_TYPE_MAP,
    blueprint_context,
    camel_case,
    column_precision,
    is_nullable,
    is_pk,
    is_unique,
    map_type,
    pascal_case,
    referenced_table,
    render_template,
    singularize,
    snake_case,
    table_columns,
    table_plural,
)

SQL_README = """# __PROJECT_NAME__ - Database Schema

PostgreSQL schema generated from the project blueprint.

## Files

- `schema.sql` - complete schema: tables, indexes, constraints and seed data
- `migrations/` - ordered migration scripts (squashed + incremental)
- `seed.sql` - sample data

## Quick start

```bash
docker compose up -d db          # start PostgreSQL
psql "$DATABASE_URL" -f schema.sql
```

## Tables

__TABLE_LIST__
"""

SQL_DOCKER_COMPOSE = """services:
  db:
    image: postgres:16-alpine
    container_name: __APP_SLUG___db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-app}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-app_password}
      POSTGRES_DB: ${POSTGRES_DB:-__APP_SLUG__}
    ports:
      - "5432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
      - ./seed.sql:/docker-entrypoint-initdb.d/02-seed.sql

volumes:
  db_data:
"""

SQL_ENV_EXAMPLE = """# PostgreSQL connection
POSTGRES_USER=app
POSTGRES_PASSWORD=app_password
POSTGRES_DB=__APP_SLUG__
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
# URL form: postgresql://user:password@host:port/database
DATABASE_URL=postgresql://app:app_password@localhost:5432/__APP_SLUG__
"""


def _fallback_create_tables(tables: list[dict[str, Any]]) -> str:
    """Build CREATE TABLE statements when the blueprint lacks sql_scripts."""
    statements: list[str] = []
    for table in tables:
        lines = []
        for column in table_columns(table):
            name = column.get("name")
            type_ = column.get("type") or "TEXT"
            lines.append(f"    {name} {type_}")
        lines.append("    PRIMARY KEY (id)" if not any(is_pk(c) for c in table_columns(table)) else "")
        body = ",\n".join(line for line in lines if line)
        statements.append(f"CREATE TABLE IF NOT EXISTS {table.get('name')} (\n{body}\n);")
    return "\n\n".join(statements)


def generate_sql(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tables = context["tables"]
    db = blueprint.get("database") or {}
    scripts = db.get("sql_scripts") or {}

    create_tables = scripts.get("create_tables") or _fallback_create_tables(tables)
    indexes = scripts.get("indexes") or ""
    constraints = scripts.get("constraints") or ""
    seed = (blueprint.get("database") or {}).get("seed_data", {}).get("sql") or ""
    if not seed:
        seed = "-- Add your seed data here"

    table_list = "\n".join(f"- `{t.get('name')}` - {t.get('description') or ''}" for t in tables)
    schema = "\n\n".join(part for part in (create_tables, indexes, constraints) if part)

    files = {
        "README.md": render_template(
            SQL_README,
            PROJECT_NAME=context["project_name"],
            TABLE_LIST=table_list,
        ),
        ".env.example": render_template(SQL_ENV_EXAMPLE, APP_SLUG=context["app_slug"]),
        "docker-compose.yml": render_template(SQL_DOCKER_COMPOSE, APP_SLUG=context["app_slug"]),
        "schema.sql": schema,
        "seed.sql": seed,
        "migrations/0001_initial.sql": f"-- Initial schema for {context['project_name']}\n\n" + create_tables,
        "migrations/0002_indexes.sql": f"-- Indexes for {context['project_name']}\n\n" + (indexes or "-- no indexes"),
        "migrations/0003_constraints.sql": f"-- Constraints for {context['project_name']}\n\n" + (constraints or "-- no constraints"),
        "migrations/0004_seed.sql": f"-- Seed data for {context['project_name']}\n\n" + seed,
        "migrations/README.md": (
            "Migrations run in filename order. Use the squashed `schema.sql` for a fresh install.\n"
            "Track applied migrations however suits your team (e.g. a `schema_migrations` table)."
        ),
    }
    return files


PRISMA_SCHEMA = """// Prisma schema for __PROJECT_NAME__
// Generated from the project blueprint. Run:
//   npx prisma migrate dev --name init
//   npx prisma generate

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

__MODELS__
"""

PRISMA_README = """# __PROJECT_NAME__ - Prisma Schema

Data model generated from the blueprint for Prisma + PostgreSQL.

## Setup

```bash
npm install
cp .env.example .env
npx prisma migrate dev --name init
npx prisma db seed
```

## Models

__MODEL_LIST__
"""

PRISMA_PACKAGE_JSON = """{
  "name": "__APP_SLUG__-prisma",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "db:generate": "prisma generate",
    "db:migrate": "prisma migrate dev",
    "db:push": "prisma db push",
    "db:seed": "node prisma/seed.js",
    "db:studio": "prisma studio"
  },
  "prisma": {
    "seed": "node prisma/seed.js"
  },
  "dependencies": {
    "@prisma/client": "^5.22.0"
  },
  "devDependencies": {
    "prisma": "^5.22.0"
  }
}
"""

PRISMA_SEED = """const { PrismaClient } = require("@prisma/client");
const prisma = new PrismaClient();

async function main() {
  // Example seed - adapt to your models
  const admin = await prisma.user.upsert({
    where: { email: "admin@example.com" },
    update: {},
    create: {
      email: "admin@example.com",
      name: "Admin",
      password_hash: "CHANGE_ME_BCRYPT_HASH",
      role: "admin",
    },
  });
  console.log("Seeded:", admin.email);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
"""

PRISMA_ENV_EXAMPLE = """# PostgreSQL connection string
DATABASE_URL="postgresql://app:app_password@localhost:5432/__APP_SLUG__"
"""

PRISMA_GITIGNORE = """node_modules/
.env
"""


def _prisma_model(table: dict[str, Any], tables_by_name: dict[str, dict[str, Any]]) -> str:
    model_name = pascal_case(singularize(table.get("name") or "item"))
    lines = [f"model {model_name} {{"]
    for column in table_columns(table):
        name = column.get("name") or ""
        prisma_type = map_type(column.get("type") or "TEXT", PRISMA_TYPE_MAP)
        attrs = []
        if is_pk(column):
            if "SERIAL" in (column.get("type") or "").upper() or "BIGSERIAL" in (column.get("type") or "").upper():
                attrs.append("@id @default(autoincrement())")
            else:
                attrs.append("@id")
        if is_unique(column):
            attrs.append("@unique")
        if name in ("created_at", "updated_at"):
            attrs.append("@default(now())")
        line = f"  {name}  {prisma_type}"
        if attrs:
            line += "  " + " ".join(attrs)
        lines.append(line)

    relation_fields = _prisma_relations(table, tables_by_name)
    lines.extend(relation_fields)
    lines.append("}")
    return "\n".join(lines)


def _prisma_relation_fk(rel: dict[str, Any], table_name: str) -> str:
    """Derive the foreign-key column name from the relationship's ``on`` clause."""
    on = rel.get("on") or ""
    match = re.search(rf"{re.escape(table_name)}\.(\w+)\s*=", on)
    if match:
        return match.group(1)
    return f"{snake_case(singularize(rel.get('to_table') or ''))}_id"


def _prisma_relations(table: dict[str, Any], tables_by_name: dict[str, dict[str, Any]]) -> list[str]:
    """Add relation fields from the blueprint's relationships section."""
    fields: list[str] = []
    relationships = table.get("relationships") or []
    for rel in relationships:
        rel_type = (rel.get("type") or "one-to-many").lower()
        target = rel.get("to_table") or ""
        if not target or target not in tables_by_name:
            continue
        target_model = pascal_case(singularize(target))
        table_name = table.get("name") or ""
        if rel_type == "one-to-many":
            fields.append(f"  {camel_case(table_plural(target))}  {target_model}[]")
            continue
        fk_name = _prisma_relation_fk(rel, table_name)
        existing = {c.get("name") for c in table_columns(table)}
        unique_attr = "  @unique" if rel_type == "one-to-one" else ""
        if fk_name not in existing:
            fields.append(f"  {fk_name}  Int?{unique_attr}")
        fields.append(
            f"  {camel_case(singularize(target))}  {target_model}?  "
            f"@relation(fields: [{fk_name}], references: [id])"
        )
    return fields


def _add_backrefs(model: str, table: dict[str, Any], tables_by_name: dict[str, dict[str, Any]]) -> str:
    """Append many-to-one back-reference lists on parent models."""
    extra: list[str] = []
    for column in table_columns(table):
        target = referenced_table(column)
        if not target or target not in tables_by_name:
            continue
        child = pascal_case(singularize(table.get("name") or "item"))
        backref = f"  {camel_case(table_plural(table.get('name') or 'item'))}  {child}[]"
        if backref not in model:
            extra.append(backref)
    if not extra:
        return model
    return model[:-1].rstrip() + "\n" + "\n".join(extra) + "\n}"


def generate_prisma(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tables_by_name: dict[str, dict[str, Any]] = {t.get("name"): t for t in context["tables"]}
    models: list[str] = []
    model_list: list[str] = []
    for table in context["tables"]:
        model = _prisma_model(table, tables_by_name)
        if table.get("name") not in {"users", "user_roles", "audit_logs"}:
            model = _add_backrefs(model, table, tables_by_name)
        models.append(model)
        model_list.append(f"- `{table.get('name')}` - {table.get('description') or ''}")

    files = {
        "README.md": render_template(
            PRISMA_README,
            PROJECT_NAME=context["project_name"],
            MODEL_LIST="\n".join(model_list),
        ),
        ".env.example": render_template(PRISMA_ENV_EXAMPLE, APP_SLUG=context["app_slug"]),
        ".gitignore": PRISMA_GITIGNORE,
        "package.json": render_template(PRISMA_PACKAGE_JSON, APP_SLUG=context["app_slug"]),
        "prisma/schema.prisma": render_template(PRISMA_SCHEMA, PROJECT_NAME=context["project_name"], MODELS="\n\n".join(models)),
        "prisma/seed.js": PRISMA_SEED,
    }
    return files


SA_MODELS_HEADER = """from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
"""

SA_MODELS_BODY = """

class __MODEL__(Base):
    __tablename__ = "__TABLE__"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
__COLUMNS__\
__RELATIONS__\
"""

SA_DATABASE = """import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app_password@localhost:5432/__APP_SLUG__")


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Session:
    with SessionLocal() as session:
        yield session
"""

SA_SEED = """import os

from sqlalchemy import text

from app.database import Base, SessionLocal, engine

# Import models so they are registered on Base.metadata
import app.models  # noqa: F401


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        # Example seed - adapt to your models
        session.execute(
            text("INSERT INTO users (email, name, role) VALUES ('admin@example.com', 'Admin', 'admin')")
            + text(" ON CONFLICT (email) DO NOTHING")
        )
        session.commit()
        print("Seeded database")


if __name__ == "__main__":
    seed()
"""

SA_REQUIREMENTS = """sqlalchemy>=2.0,<3.0
psycopg2-binary>=2.9
alembic>=1.13
python-dotenv>=1.0
"""

SA_README = """# __PROJECT_NAME__ - SQLAlchemy Models

SQLAlchemy 2.0 ORM models generated from the blueprint.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
cp .env.example .env
python -m app.seed            # create tables + seed
```

Use Alembic for migrations:

```bash
alembic init migrations
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

## Models

__MODEL_LIST__
"""

SA_ALEMBIC_INI = """[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = postgresql://app:app_password@localhost:5432/__APP_SLUG__

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

SA_ALEMBIC_ENV = """from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""


def _sa_column(column: dict[str, Any], is_pk: bool) -> str:
    name = column.get("name")
    type_raw = column.get("type") or "TEXT"
    base = map_type(type_raw, SA_TYPE_MAP)
    precision = column_precision(type_raw)
    if base == "String" and precision:
        mapped = f"String({precision})"
    elif base == "Numeric" and precision:
        mapped = f"Numeric({precision})"
    else:
        mapped = base
    args = [mapped]
    if is_pk:
        args.append("primary_key=True")
    if is_unique(column):
        args.append("unique=True")
    if not is_nullable(column) and not is_pk and "now()" not in type_raw.upper():
        args.append("nullable=False")
    if "now()" in type_raw.upper():
        args.append("server_default=func.now()")
    target = referenced_table(column)
    if target:
        args.append(f'ForeignKey("{target}.id")')
    return f"    {name}: Mapped[Optional[{base}]] = mapped_column({', '.join(args)})"


def _sa_model(table: dict[str, Any], tables_by_name: dict[str, dict[str, Any]]) -> str:
    model = pascal_case(singularize(table.get("name") or "item"))
    pk_cols = [c for c in table_columns(table) if is_pk(c)]

    cols: list[str] = []
    for column in table_columns(table):
        cols.append(_sa_column(column, bool(pk_cols) and column.get("name") == "id"))

    relations: list[str] = []
    relationships = table.get("relationships") or []
    for rel in relationships:
        rel_type = (rel.get("type") or "one-to-many").lower()
        target = rel.get("to_table") or ""
        if not target or target not in tables_by_name:
            continue
        target_model = pascal_case(singularize(target))
        if rel_type == "one-to-many":
            relations.append(
                f"    {camel_case(table_plural(target))}: Mapped[list['{target_model}']] = "
                f'relationship(back_populates="{camel_case(singularize(table.get("name") or "item"))}")'
            )
        else:
            relations.append(
                f"    {camel_case(singularize(target))}: Mapped[Optional['{target_model}']] = "
                f'relationship(back_populates="{camel_case(table_plural(table.get("name") or "item"))}")'
            )

    col_lines = "\n".join(cols) if cols else ""
    rel_lines = ("\n" + "\n".join(relations)) if relations else ""
    return render_template(
        SA_MODELS_BODY,
        MODEL=model,
        TABLE=table.get("name"),
        COLUMNS=col_lines,
        RELATIONS=rel_lines,
    )


def generate_sqlalchemy(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tables_by_name = {t.get("name"): t for t in context["tables"]}
    models = [SA_MODELS_HEADER]
    for table in context["tables"]:
        models.append(_sa_model(table, tables_by_name))
    model_list = "\n".join(f"- `{t.get('name')}` - {t.get('description') or ''}" for t in context["tables"])

    return {
        "README.md": render_template(
            SA_README,
            PROJECT_NAME=context["project_name"],
            MODEL_LIST=model_list,
        ),
        ".env.example": render_template(SQL_ENV_EXAMPLE, APP_SLUG=context["app_slug"]),
        ".gitignore": ".venv/\n__pycache__/\n.env\n",
        "requirements.txt": SA_REQUIREMENTS,
        "app/__init__.py": "",
        "app/database.py": render_template(SA_DATABASE, APP_SLUG=context["app_slug"]),
        "app/models.py": "\n".join(models),
        "app/seed.py": SA_SEED,
        "alembic.ini": render_template(SA_ALEMBIC_INI, APP_SLUG=context["app_slug"]),
        "migrations/env.py": SA_ALEMBIC_ENV,
        "migrations/script.py.mako": (
            '"""${message}"""\n\nfrom alembic import op\nimport sqlalchemy as sa\n'
            "${imports if imports else ''}\n\nrevision = ${repr(up_revision)}\n"
            "down_revision = ${repr(down_revision)}\n"
            "branch_labels = ${repr(branch_labels)}\n"
            "depends_on = ${repr(depends_on)}\n\n\n"
            "def upgrade() -> None:\n    ${upgrades if upgrades else 'pass'}\n\n\n"
            "def downgrade() -> None:\n    ${downgrades if downgrades else 'pass'}\n"
        ),
        "migrations/versions/.gitkeep": "",
    }
