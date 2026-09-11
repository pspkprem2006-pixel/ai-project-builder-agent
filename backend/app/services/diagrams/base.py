"""Shared helpers for the diagram generation service.

Diagrams are *always* generated on demand from the current blueprint, so they
stay synchronized automatically: whenever the blueprint changes, the next
request produces an up-to-date diagram.
"""

from __future__ import annotations

import re
from typing import Any


def escape_label(text: Any, max_length: int = 60) -> str:
    """Sanitize a free-text string for use inside a Mermaid label."""
    if text is None:
        return ""
    value = str(text).strip().replace("\n", " ")
    value = value.replace('"', "'").replace("[", "(").replace("]", ")")
    value = value.replace("{", "(").replace("}", ")").replace(";", ",")
    if len(value) > max_length:
        value = value[: max_length - 1].rstrip() + "…"
    return value


def node_id(text: Any) -> str:
    """Turn arbitrary text into a valid Mermaid node identifier."""
    value = re.sub(r"[^a-zA-Z0-9_]", "_", str(text).strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "node"


def section(blueprint: dict[str, Any], key: str) -> dict[str, Any]:
    value = blueprint.get(key)
    return value if isinstance(value, dict) else {}


def project_info(blueprint: dict[str, Any]) -> dict[str, Any]:
    project = blueprint.get("project")
    if not isinstance(project, dict):
        return {}
    return project


def stack(blueprint: dict[str, Any]) -> dict[str, str]:
    info = project_info(blueprint)
    value = info.get("stack")
    return value if isinstance(value, dict) else {}


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def tables(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    db = section(blueprint, "database")
    items = db.get("tables")
    if not isinstance(items, list):
        return []
    return [t for t in items if isinstance(t, dict) and t.get("name")]


def columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    items = table.get("columns")
    if not isinstance(items, list):
        return []
    return [c for c in items if isinstance(c, dict) and c.get("name")]


def is_pk(column: dict[str, Any]) -> bool:
    raw = str(column.get("type") or "").upper()
    constraints = column.get("constraints") or []
    return "PRIMARY KEY" in raw or "PK" in str(constraints).upper()


def is_fk(column: dict[str, Any]) -> bool:
    return "REFERENCES" in str(column.get("type") or "").upper()


def referenced_table(column: dict[str, Any]) -> str | None:
    match = re.search(
        r"REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        str(column.get("type") or ""),
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def relationship_links(blueprint: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (source_table, target_table, relationship_type) triples."""
    links: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for table in tables(blueprint):
        source = str(table.get("name") or "")
        rels = table.get("relationships")
        if isinstance(rels, list):
            for rel in rels:
                if not isinstance(rel, dict):
                    continue
                target = str(rel.get("to_table") or "")
                rel_type = str(rel.get("type") or "one-to-many")
                if source and target and (source, target) not in seen:
                    seen.add((source, target))
                    links.append((source, target, rel_type))
        for column in columns(table):
            target = referenced_table(column)
            if target and source and target != source and (source, target) not in seen:
                seen.add((source, target))
                links.append((source, target, "one-to-many"))
    return links


def endpoints(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    api = section(blueprint, "api")
    items = api.get("endpoints")
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict) and e.get("path") and e.get("method")]


def components(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    arch = section(blueprint, "architecture")
    items = arch.get("components")
    if not isinstance(items, list):
        return []
    return [c for c in items if isinstance(c, dict) and c.get("name")]


def workflows(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    bp = section(blueprint, "business_processes")
    items = bp.get("workflows")
    if not isinstance(items, list):
        return []
    return [w for w in items if isinstance(w, dict) and w.get("name")]


def blueprint_meta(blueprint: dict[str, Any]) -> dict[str, Any]:
    metadata = blueprint.get("metadata")
    return metadata if isinstance(metadata, dict) else {}
