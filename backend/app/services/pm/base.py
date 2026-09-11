"""Blueprint extractors for the project management generator.

The PM model is generated on demand from the blueprint, so it always mirrors
the latest blueprint — regeneration is automatic by construction.
"""

from __future__ import annotations

from typing import Any

from app.services.diagrams.base import project_info, section  # noqa: F401  (re-exported)


def _item_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def functional_requirements(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = section(blueprint, "analysis")
    items = analysis.get("functional_requirements")
    if not isinstance(items, list):
        return []
    return [fr for fr in items if isinstance(fr, dict) and fr.get("title")]


def roadmap_milestones(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    roadmap = section(blueprint, "roadmap")
    items = roadmap.get("weekly_milestones")
    if not isinstance(items, list):
        return []
    return [m for m in items if isinstance(m, dict) and (m.get("theme") or m.get("name"))]


def milestone_tasks(milestone: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task in milestone.get("tasks") or []:
        if isinstance(task, str) and task.strip():
            tasks.append({"task": task.strip(), "hours": 8, "deliverable": ""})
        elif isinstance(task, dict) and task.get("task"):
            hours = task.get("hours")
            tasks.append(
                {
                    "task": str(task["task"]).strip(),
                    "hours": int(hours) if isinstance(hours, (int, float)) and hours > 0 else 8,
                    "deliverable": str(task.get("deliverable") or ""),
                }
            )
    return tasks


def workflows(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    processes = section(blueprint, "business_processes")
    items = processes.get("workflows")
    if not isinstance(items, list):
        return []
    return [w for w in items if isinstance(w, dict) and w.get("name")]


def actors(blueprint: dict[str, Any]) -> list[str]:
    result: list[str] = []
    domain = section(blueprint, "domain_understanding")
    for item in domain.get("primary_users") or []:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    roles = section(blueprint, "business_processes").get("roles")
    if isinstance(roles, list):
        result.extend(str(r) for r in roles if str(r).strip())
    for workflow in workflows(blueprint):
        for actor in workflow.get("actors") or []:
            if isinstance(actor, str) and actor.strip():
                result.append(actor.strip())
    unique: list[str] = []
    for value in result:
        if value not in unique:
            unique.append(value)
    return unique


def endpoints(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    api = section(blueprint, "api")
    items = api.get("endpoints")
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict) and e.get("path") and e.get("method")]


def tables(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    db = section(blueprint, "database")
    items = db.get("tables")
    if not isinstance(items, list):
        return []
    return [t for t in items if isinstance(t, dict) and t.get("name")]


def auth_configured(blueprint: dict[str, Any]) -> bool:
    info = project_info(blueprint)
    stack = info.get("stack")
    if isinstance(stack, dict) and stack.get("auth"):
        return True
    api = section(blueprint, "api")
    auth = api.get("auth")
    return bool(auth) and bool(auth.get("method") if isinstance(auth, dict) else auth)


def database_configured(blueprint: dict[str, Any]) -> bool:
    return bool(tables(blueprint))


def project_description(blueprint: dict[str, Any]) -> str:
    info = project_info(blueprint)
    return str(info.get("description") or "").strip()
