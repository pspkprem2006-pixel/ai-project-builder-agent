"""Shared helpers for the AI code generation engine.

Every generator receives the structured blueprint dict and returns a mapping
of file path -> file content, which the API layer packages into a ZIP archive.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def slugify(value: str) -> str:
    """kebab-case slug safe for file and package names."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "app"


def snake_case(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned or "app"


def pascal_case(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in snake_case(value).split("_") if part) or "App"


def camel_case(value: str) -> str:
    pascal = pascal_case(value)
    return pascal[:1].lower() + pascal[1:]


def pluralize(value: str) -> str:
    """Very small pluralizer good enough for table names.

    Expects a singular noun (use :func:`singularize` first if the input may
    already be plural).
    """
    value = value or ""
    if value.endswith("y") and not value.endswith(("ay", "ey", "oy", "uy")):
        return value[:-1] + "ies"
    if value.endswith(("s", "x", "z", "ch", "sh")):
        return value + "es"
    return value + "s"


def table_plural(name: str) -> str:
    """Pluralize a table name that may already be plural."""
    return pluralize(singularize(name))


def singularize(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("ses") and len(value) > 3:
        return value[:-2]
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def java_package(name: str) -> str:
    parts = [re.sub(r"[^a-zA-Z0-9]+", "", p).lower() for p in name.split() if p]
    parts = [p for p in parts if p]
    return "com.example." + (".".join(parts[:2]) or "app")


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def render_template(template: str, **tokens: str) -> str:
    """Replace ``__TOKEN__`` placeholders so generated code keeps its braces."""
    for key, value in tokens.items():
        template = template.replace(f"__{key}__", value)
    return template


# ---------------------------------------------------------------------------
# ZIP packaging
# ---------------------------------------------------------------------------


def safe_zip_path(path: str) -> str:
    """Validate a ZIP entry path before it is archived.

    Entry names derive from generator code plus LLM/user-influenced content
    (table names, project names). A crafted blueprint must never be able to
    smuggle ``../``, absolute, backslash or Windows drive-letter paths into a
    generated archive — those escape the intended output directory when a
    user extracts the ZIP.
    """
    if not isinstance(path, str) or not path:
        raise ValueError("ZIP entry path must be a non-empty string")
    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError(f"Unsafe ZIP entry path: {path!r}")
    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        raise ValueError(f"Unsafe ZIP entry path: {path!r}")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError(f"Unsafe ZIP entry path: {path!r}")
    return normalized


def build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            zf.writestr(safe_zip_path(path), files[path])
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Column type mapping
# ---------------------------------------------------------------------------


def parse_column_type(raw: str) -> tuple[str, str | None]:
    """Return ``(BASE_TYPE_UPPER, precision)`` from a PostgreSQL column type."""
    raw = (raw or "TEXT").strip().upper()
    match = re.match(r"([A-Z]+)(?:\(([^)]*)\))?", raw)
    base = match.group(1) if match else "TEXT"
    precision = match.group(2) if match and match.group(2) else None
    return base, precision


PY_TYPE_MAP: dict[str, str] = {
    "SERIAL": "int",
    "BIGSERIAL": "int",
    "SMALLSERIAL": "int",
    "INTEGER": "int",
    "INT": "int",
    "BIGINT": "int",
    "SMALLINT": "int",
    "TEXT": "str",
    "VARCHAR": "str",
    "CHAR": "str",
    "UUID": "str",
    "BOOLEAN": "bool",
    "BOOL": "bool",
    "TIMESTAMP": "datetime",
    "TIMESTAMPTZ": "datetime",
    "DATE": "date",
    "TIME": "time",
    "NUMERIC": "Decimal",
    "DECIMAL": "Decimal",
    "FLOAT": "float",
    "DOUBLE": "float",
    "DOUBLE PRECISION": "float",
    "REAL": "float",
    "JSONB": "Any",
    "JSON": "Any",
    "BYTEA": "bytes",
}

SA_TYPE_MAP: dict[str, str] = {
    "SERIAL": "Integer",
    "BIGSERIAL": "BigInteger",
    "SMALLSERIAL": "SmallInteger",
    "INTEGER": "Integer",
    "INT": "Integer",
    "BIGINT": "BigInteger",
    "SMALLINT": "SmallInteger",
    "TEXT": "Text",
    "VARCHAR": "String",
    "CHAR": "String",
    "UUID": "Uuid",
    "BOOLEAN": "Boolean",
    "BOOL": "Boolean",
    "TIMESTAMP": "DateTime(timezone=True)",
    "TIMESTAMPTZ": "DateTime(timezone=True)",
    "DATE": "Date",
    "TIME": "Time",
    "NUMERIC": "Numeric",
    "DECIMAL": "Numeric",
    "FLOAT": "Float",
    "DOUBLE": "Float",
    "DOUBLE PRECISION": "Float",
    "REAL": "Float",
    "JSONB": "JSONB",
    "JSON": "JSON",
    "BYTEA": "LargeBinary",
}

PRISMA_TYPE_MAP: dict[str, str] = {
    "SERIAL": "Int",
    "BIGSERIAL": "BigInt",
    "SMALLSERIAL": "Int",
    "INTEGER": "Int",
    "INT": "Int",
    "BIGINT": "BigInt",
    "SMALLINT": "Int",
    "TEXT": "String",
    "VARCHAR": "String",
    "CHAR": "String",
    "UUID": "String",
    "BOOLEAN": "Boolean",
    "BOOL": "Boolean",
    "TIMESTAMP": "DateTime",
    "TIMESTAMPTZ": "DateTime",
    "DATE": "DateTime",
    "TIME": "DateTime",
    "NUMERIC": "Decimal",
    "DECIMAL": "Decimal",
    "FLOAT": "Float",
    "DOUBLE": "Float",
    "DOUBLE PRECISION": "Float",
    "REAL": "Float",
    "JSONB": "Json",
    "JSON": "Json",
    "BYTEA": "Bytes",
}

JAVA_TYPE_MAP: dict[str, str] = {
    "SERIAL": "Long",
    "BIGSERIAL": "Long",
    "SMALLSERIAL": "Integer",
    "INTEGER": "Integer",
    "INT": "Integer",
    "BIGINT": "Long",
    "SMALLINT": "Integer",
    "TEXT": "String",
    "VARCHAR": "String",
    "CHAR": "String",
    "UUID": "UUID",
    "BOOLEAN": "Boolean",
    "BOOL": "Boolean",
    "TIMESTAMP": "Instant",
    "TIMESTAMPTZ": "Instant",
    "DATE": "LocalDate",
    "TIME": "LocalTime",
    "NUMERIC": "BigDecimal",
    "DECIMAL": "BigDecimal",
    "FLOAT": "Double",
    "DOUBLE": "Double",
    "DOUBLE PRECISION": "Double",
    "REAL": "Double",
    "JSONB": "String",
    "JSON": "String",
    "BYTEA": "byte[]",
}

JAVA_IMPORT_MAP: dict[str, set[str]] = {
    "Instant": {"java.time.Instant"},
    "LocalDate": {"java.time.LocalDate"},
    "LocalTime": {"java.time.LocalTime"},
    "BigDecimal": {"java.math.BigDecimal"},
    "UUID": {"java.util.UUID"},
}

TS_TYPE_MAP: dict[str, str] = {
    "SERIAL": "number",
    "BIGSERIAL": "number",
    "SMALLSERIAL": "number",
    "INTEGER": "number",
    "INT": "number",
    "BIGINT": "number",
    "SMALLINT": "number",
    "TEXT": "string",
    "VARCHAR": "string",
    "CHAR": "string",
    "UUID": "string",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
    "TIMESTAMP": "string",
    "TIMESTAMPTZ": "string",
    "DATE": "string",
    "TIME": "string",
    "NUMERIC": "number",
    "DECIMAL": "number",
    "FLOAT": "number",
    "DOUBLE": "number",
    "DOUBLE PRECISION": "number",
    "REAL": "number",
    "JSONB": "Record<string, unknown>",
    "JSON": "Record<string, unknown>",
    "BYTEA": "string",
}


def map_type(raw: str, mapping: dict[str, str]) -> str:
    base, _ = parse_column_type(raw)
    return mapping.get(base, "str")


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------


def is_pk(column: dict[str, Any]) -> bool:
    type_upper = (column.get("type") or "").upper()
    return "PRIMARY KEY" in type_upper or any(
        c.upper() == "PK" for c in column.get("constraints", [])
    )


def is_unique(column: dict[str, Any]) -> bool:
    return any(c.upper() == "UNIQUE" for c in column.get("constraints", []))


def is_nullable(column: dict[str, Any]) -> bool:
    return "NOT NULL" not in (column.get("type") or "").upper()


def column_precision(raw: str) -> int | None:
    _, precision = parse_column_type(raw)
    if precision is None:
        return None
    first = precision.split(",")[0].strip()
    return int(first) if first.isdigit() else None


def column_description(column: dict[str, Any]) -> str:
    return (column.get("description") or column.get("name") or "").strip()


# ---------------------------------------------------------------------------
# Blueprint context
# ---------------------------------------------------------------------------

DEFAULT_COLUMNS = [
    {
        "name": "id",
        "type": "SERIAL PRIMARY KEY",
        "constraints": ["PK"],
        "description": "Primary key",
    },
    {
        "name": "created_at",
        "type": "TIMESTAMPTZ DEFAULT now()",
        "constraints": [],
        "description": "Row creation timestamp",
    },
]

DEFAULT_TABLE = {
    "name": "items",
    "description": "Core entity of the application",
    "columns": DEFAULT_COLUMNS,
    "indexes": [],
    "relationships": [],
}

DEFAULT_ENDPOINT = {
    "method": "GET",
    "path": "/api/v1/items",
    "description": "List items",
    "authentication": True,
    "status_codes": [200],
    "validation_rules": [],
}


def blueprint_context(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Flatten the blueprint into a friendly context for generators."""
    project = blueprint.get("project") or {}
    stack = project.get("stack") or {}
    analysis = blueprint.get("analysis") or {}
    db = blueprint.get("database") or {}
    api = blueprint.get("api") or {}
    ui = blueprint.get("ui_ux") or {}

    tables = [t for t in (db.get("tables") or []) if isinstance(t, dict) and t.get("name")]
    if not tables:
        tables = [DEFAULT_TABLE]
    endpoints = [e for e in (api.get("endpoints") or []) if isinstance(e, dict) and e.get("path")]
    if not endpoints:
        endpoints = [DEFAULT_ENDPOINT]

    excluded = {"user_roles", "audit_logs", "users"}
    crud_tables = [t for t in tables if t.get("name") not in excluded]
    primary = crud_tables[0] if crud_tables else tables[0]

    name = project.get("name") or "AI Blueprint App"
    auth_method = stack.get("auth") or api.get("auth", {}).get("method") or "JWT"

    return {
        "project_name": name,
        "app_slug": slugify(name),
        "app_class": pascal_case(name),
        "app_package": java_package(name),
        "stack": stack,
        "tables": tables,
        "crud_tables": crud_tables,
        "primary_table": primary,
        "endpoints": endpoints,
        "auth_method": auth_method,
        "database": stack.get("database") or "PostgreSQL",
        "frontend": stack.get("frontend") or "React",
        "backend": stack.get("backend") or "FastAPI",
        "analysis": analysis,
        "ui": ui,
        "requirements": analysis.get("requirements") or [],
        "features": analysis.get("features") or [],
    }


def table_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    columns = table.get("columns") or []
    columns = [c for c in columns if isinstance(c, dict) and c.get("name")]
    if not columns:
        columns = list(DEFAULT_COLUMNS)
    return columns


def non_pk_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in table_columns(table) if not is_pk(c)]


def relation_columns(table: dict[str, Any]) -> list[str]:
    """Columns that reference another table, e.g. ``patient_id``."""
    result: list[str] = []
    for column in table_columns(table):
        if "REFERENCES" in (column.get("type") or "").upper():
            result.append(column.get("name") or "")
    return result


def referenced_table(column: dict[str, Any]) -> str | None:
    match = re.search(r"REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)", (column.get("type") or "").upper())
    return match.group(1) if match else None
