"""Project management model generator.

Builds a complete PM artifact set — epics, user stories, acceptance criteria,
sprint backlog, GitHub issues, Jira tasks, milestones, dependencies, critical
path and burndown-ready estimates — from the stored blueprint. Every task
references the blueprint modules it was derived from.
"""

from __future__ import annotations

from typing import Any

from app.services.diagrams.base import project_info
from app.services.pm import base as pmb

SPRINT_SIZE = 8

EPIC_RANK = {
    "database": 0,
    "auth": 1,
    "core": 2,
    "api": 3,
    "ui_ux": 4,
    "testing": 5,
    "documentation": 6,
    "deployment": 7,
}

MODULE_SECTIONS: dict[str, list[str]] = {
    "auth": ["api", "security"],
    "database": ["database"],
    "core": ["business_processes", "roadmap"],
    "api": ["api"],
    "ui_ux": ["ui_ux"],
    "testing": ["testing"],
    "documentation": ["documentation"],
    "deployment": ["deployment"],
}

MODULE_LABELS: dict[str, str] = {
    "auth": "Authentication",
    "database": "Database",
    "core": "Core",
    "api": "API",
    "ui_ux": "UI/UX",
    "testing": "Testing",
    "documentation": "Documentation",
    "deployment": "Deployment",
}


def _infer_module(text: str, fallback: str) -> str:
    lowered = text.lower()
    if any(
        keyword in lowered
        for keyword in (
            "login",
            "register",
            "signup",
            "sign in",
            "session",
            "oauth",
            "jwt",
            "token",
            "auth",
            "password",
            "account",
        )
    ):
        return "auth"
    if any(
        keyword in lowered
        for keyword in ("schema", "table", "database", "data model", "migration", "seed", "index", "entity")
    ):
        return "database"
    if any(
        keyword in lowered
        for keyword in (
            "frontend",
            "screen",
            "page",
            "form",
            "ui",
            "interface",
            "design",
            "layout",
            "component",
        )
    ):
        return "ui_ux"
    if any(
        keyword in lowered
        for keyword in ("api", "endpoint", "integration", "service", "webhook", "rest", "backend")
    ):
        return "api"
    if "test" in lowered:
        return "testing"
    if any(
        keyword in lowered
        for keyword in ("deploy", "ci", "docker", "devops", "infra", "monitor", "release", "pipeline")
    ):
        return "deployment"
    if any(keyword in lowered for keyword in ("doc", "readme", "guide", "manual")):
        return "documentation"
    return fallback


def _points_for_hours(hours: int) -> int:
    if hours <= 2:
        return 1
    if hours <= 4:
        return 2
    if hours <= 6:
        return 3
    if hours <= 8:
        return 5
    if hours <= 12:
        return 8
    if hours <= 16:
        return 13
    return 21


def _priority(points: int) -> str:
    if points <= 2:
        return "Low"
    if points <= 5:
        return "Medium"
    return "High"


def _project_key(name: str) -> str:
    words = [w for w in str(name or "").replace("-", " ").replace("_", " ").split() if w]
    if not words:
        return "PROJ"
    letters = [c for c in words[0] if c.isalpha()][:4]
    if len(words) > 1 and len(letters) < 4:
        for c in words[1]:
            if len(letters) >= 4:
                break
            if c.isalpha():
                letters.append(c)
    key = "".join(letters).upper()
    return key or "PROJ"


def _acceptance_criteria(story: dict[str, Any]) -> list[str]:
    module = story["module"]
    title = story["title"].lower()
    action = story.get("i_want") or story["title"]
    if module == "auth":
        return [
            "Given I have no active session, when I request a protected area, then I am redirected to login",
            "Given I have valid credentials, when I submit them, then I receive a session token and access",
            "Given I submit invalid credentials, when I try to log in, then an error is shown and no session is created",
        ]
    if module == "database":
        return [
            f"Given the {title} schema, when migrations are applied, then tables, keys and indexes exist",
            "Given reference data, when the seed script runs, then the database contains reproducible sample data",
            "Given existing rows, when data is written, then integrity rules (PK/FK/unique) are enforced",
        ]
    if module == "api":
        return [
            f"Given a valid request, when {action} is called, then the expected status code and payload are returned",
            "Given an invalid payload, when the endpoint is called, then validation errors are returned",
            "Given no session, when a protected endpoint is called, then a 401/403 response is returned",
        ]
    if module == "ui_ux":
        return [
            f"Given I open the {story['title']} screen, when it loads, then the content reflects the blueprint's UI/UX plan",
            "Given the screen is open, when I interact with it, then state updates are reflected immediately",
            "Given a smaller viewport, when the screen renders, then it stays usable and responsive",
        ]
    return [
        f"Given I am working in the {MODULE_LABELS.get(module, module)} module, when {title} is completed, "
        "then the documented behavior is available",
        "Given the task is implemented, when it is exercised end-to-end, then it works without errors",
        "Given the blueprint module changes, when this task is revisited, then it stays consistent with the blueprint",
    ]


def _build_epics(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    epics: list[dict[str, Any]] = []
    milestones = pmb.roadmap_milestones(blueprint)
    if milestones:
        for index, milestone in enumerate(milestones, start=1):
            title = str(milestone.get("theme") or milestone.get("name") or f"Milestone {index}")
            week = milestone.get("week")
            epics.append(
                {
                    "id": f"EPIC-{index}",
                    "title": title,
                    "description": str(milestone.get("goal") or ""),
                    "week": int(week) if isinstance(week, (int, float)) else index,
                    "module": _infer_module(title, "core"),
                    "source_sections": ["roadmap"],
                    "tasks": pmb.milestone_tasks(milestone),
                    "source": "roadmap",
                }
            )
    else:
        requirements = pmb.functional_requirements(blueprint)
        for index, requirement in enumerate(requirements, start=1):
            title = str(requirement.get("title") or f"Requirement {index}")
            epics.append(
                {
                    "id": f"EPIC-{index}",
                    "title": title,
                    "description": str(requirement.get("description") or ""),
                    "week": index,
                    "module": _infer_module(title, "core"),
                    "source_sections": ["analysis"],
                    "tasks": [{"task": title, "hours": 8, "deliverable": ""}],
                    "source": "requirements",
                }
            )
    return epics


def _add_system_epics(blueprint: dict[str, Any], epics: list[dict[str, Any]]) -> None:
    has_auth = any(epic["module"] == "auth" for epic in epics)
    has_db = any(epic["module"] == "database" for epic in epics)

    if pmb.auth_configured(blueprint) and not has_auth:
        epics.insert(
            0,
            {
                "id": "EPIC-AUTH",
                "title": "Authentication & Accounts",
                "description": "User registration, login and session security.",
                "week": 0,
                "module": "auth",
                "source_sections": ["api", "security"],
                "tasks": [
                    {
                        "task": "Register an account",
                        "hours": 8,
                        "deliverable": "Registration endpoint and form",
                    },
                    {
                        "task": "Log in and manage sessions",
                        "hours": 8,
                        "deliverable": "Login flow and tokens",
                    },
                    {
                        "task": "Reset password and manage profile",
                        "hours": 6,
                        "deliverable": "Account management",
                    },
                ],
                "source": "system",
            },
        )

    if pmb.database_configured(blueprint) and not has_db:
        db_tasks: list[dict[str, Any]] = []
        for table in pmb.tables(blueprint)[:6]:
            db_tasks.append(
                {"task": f"Create schema for {table.get('name')}", "hours": 4, "deliverable": "DDL"}
            )
        db_tasks.append(
            {"task": "Write migrations and seed data", "hours": 6, "deliverable": "Migrated database"}
        )
        epics.insert(
            0,
            {
                "id": "EPIC-DB",
                "title": "Database Schema & Data Layer",
                "description": "Schema, migrations, indexes and seed data.",
                "week": 0,
                "module": "database",
                "source_sections": ["database"],
                "tasks": db_tasks,
                "source": "system",
            },
        )


def _build_stories(epics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stories: list[dict[str, Any]] = []
    counter = 1
    for epic in epics:
        tasks = epic.get("tasks") or []
        if not tasks:
            tasks = [{"task": epic["title"], "hours": 8, "deliverable": ""}]
        for task in tasks:
            title = str(task.get("task") or epic["title"])
            hours = int(task.get("hours") or 8)
            module = _infer_module(title, epic["module"])
            points = _points_for_hours(hours)
            story = {
                "id": f"US-{counter}",
                "title": title,
                "as_a": "User",
                "i_want": title,
                "so_that": epic.get("description")
                or f"complete the {MODULE_LABELS.get(module, module)} module",
                "module": module,
                "source_sections": MODULE_SECTIONS.get(module, ["roadmap"]),
                "epic_id": epic["id"],
                "points": points,
                "hours": hours,
                "priority": _priority(points),
            }
            story["acceptance_criteria"] = _acceptance_criteria(story)
            stories.append(story)
            counter += 1
    return stories


def _build_sprints(
    stories: list[dict[str, Any]], epics_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    sprints: list[dict[str, Any]] = []
    for index in range(0, len(stories), SPRINT_SIZE):
        chunk = stories[index : index + SPRINT_SIZE]
        sprint_number = index // SPRINT_SIZE + 1
        epic_titles: list[str] = []
        for story in chunk:
            epic = epics_by_id.get(story["epic_id"])
            title = epic.get("title") if epic else story["epic_id"]
            if title not in epic_titles:
                epic_titles.append(title)
        sprints.append(
            {
                "sprint": sprint_number,
                "name": f"Sprint {sprint_number}",
                "goal": "Deliver: " + ", ".join(epic_titles[:3]),
                "story_ids": [story["id"] for story in chunk],
                "total_points": sum(story["points"] for story in chunk),
                "total_hours": sum(story["hours"] for story in chunk),
            }
        )
    return sprints


def _build_dependencies(stories: list[dict[str, Any]], epics: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_epic: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        by_epic.setdefault(story["epic_id"], []).append(story)

    edges: set[tuple[str, str]] = set()
    ordered_epics = sorted(
        epics,
        key=lambda epic: (EPIC_RANK.get(epic["module"], 9), str(epic["id"])),
    )

    chain_position: dict[str, int] = {}
    position = 0
    for epic in ordered_epics:
        for story in by_epic.get(epic["id"], []):
            chain_position[story["id"]] = position
            position += 1

    previous_tail: str | None = None
    for epic in ordered_epics:
        ids = [story["id"] for story in by_epic.get(epic["id"], [])]
        if not ids:
            continue
        for first, second in zip(ids, ids[1:], strict=False):
            edges.add((first, second))
        if previous_tail:
            edges.add((previous_tail, ids[0]))
        previous_tail = ids[-1]

    module_stories: dict[str, list[str]] = {}
    for story in stories:
        module_stories.setdefault(story["module"], []).append(story["id"])

    def _cross_edge(source_module: str, target_module: str) -> None:
        sources = module_stories.get(source_module, [])
        targets = module_stories.get(target_module, [])
        if not sources or not targets:
            return
        source, target = sources[-1], targets[0]
        if chain_position[source] < chain_position[target]:
            edges.add((source, target))

    _cross_edge("database", "api")
    _cross_edge("auth", "api")

    return [{"from": source, "to": target, "type": "depends_on"} for source, target in sorted(edges)]


def _critical_path(stories: list[dict[str, Any]], dependencies: list[dict[str, str]]) -> dict[str, Any]:
    by_id = {story["id"]: story for story in stories}
    if not by_id:
        return {"chain": [], "total_hours": 0, "total_points": 0}
    adjacency: dict[str, list[str]] = {story["id"]: [] for story in stories}
    indegree: dict[str, int] = {story["id"]: 0 for story in stories}
    for edge in dependencies:
        source, target = edge["from"], edge["to"]
        if source in by_id and target in by_id:
            adjacency[source].append(target)
            indegree[target] += 1

    queue = sorted([sid for sid, degree in indegree.items() if degree == 0])
    topo: list[str] = []
    while queue:
        node = queue.pop(0)
        topo.append(node)
        for neighbor in sorted(adjacency[node]):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    remaining = [sid for sid in by_id if sid not in topo]
    topo.extend(sorted(remaining))

    longest: dict[str, int] = {sid: by_id[sid]["hours"] for sid in topo}
    parent: dict[str, str | None] = {sid: None for sid in topo}
    for sid in topo:
        for neighbor in adjacency[sid]:
            candidate = longest[sid] + by_id[neighbor]["hours"]
            if candidate > longest[neighbor]:
                longest[neighbor] = candidate
                parent[neighbor] = sid

    end = max(longest, key=lambda sid: longest[sid])
    chain: list[str] = []
    node: str | None = end
    seen: set[str] = set()
    while node and node not in seen:
        chain.append(node)
        seen.add(node)
        node = parent[node]
    chain.reverse()
    return {
        "chain": chain,
        "total_hours": longest[end],
        "total_points": sum(by_id[sid]["points"] for sid in chain),
    }


def _build_github_issues(
    stories: list[dict[str, Any]], epics_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    number = 1
    for story in stories:
        epic = epics_by_id.get(story["epic_id"])
        body_lines = [
            f"**Epic:** {story['epic_id']} — {epic.get('title') if epic else ''}",
            f"**Blueprint modules:** {', '.join(story['source_sections'])}",
            "",
            "**Acceptance criteria:**",
        ]
        for criterion in story["acceptance_criteria"]:
            body_lines.append(f"- [ ] {criterion}")
        issues.append(
            {
                "number": number,
                "title": story["title"],
                "type": "story",
                "labels": [story["epic_id"].lower(), story["module"]],
                "body": "\n".join(body_lines),
                "story_id": story["id"],
            }
        )
        number += 1
    chores = [
        ("Set up repository and CI pipeline", ["chore", "devops"]),
        ("Add README and contribution guide", ["chore", "documentation"]),
        ("Configure secrets and environment template", ["chore", "devops"]),
    ]
    for title, labels in chores:
        issues.append(
            {
                "number": number,
                "title": title,
                "type": "chore",
                "labels": labels,
                "body": "**Blueprint modules:** deployment\n\nProject hygiene task derived from the deployment module.",
                "story_id": None,
            }
        )
        number += 1
    return issues


def _build_jira_tasks(
    epics: list[dict[str, Any]],
    stories: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    counter = 1
    for epic in epics:
        tasks.append(
            {
                "key": f"{key}-{counter}",
                "summary": epic["title"],
                "type": "Epic",
                "story_points": 0,
                "epic": epic["id"],
                "status": "To Do",
                "labels": [epic["module"]],
            }
        )
        counter += 1
    for story in stories:
        tasks.append(
            {
                "key": f"{key}-{counter}",
                "summary": story["title"],
                "type": "Story",
                "story_points": story["points"],
                "epic": story["epic_id"],
                "status": "To Do",
                "labels": [story["module"]],
            }
        )
        counter += 1
    for index, chore in enumerate(
        [
            "Set up repository and CI pipeline",
            "Add README and contribution guide",
            "Configure secrets and environment template",
        ],
        start=counter,
    ):
        tasks.append(
            {
                "key": f"{key}-{index}",
                "summary": chore,
                "type": "Chore",
                "story_points": 1,
                "epic": None,
                "status": "To Do",
                "labels": ["chore"],
            }
        )
    return tasks


def _build_milestones(
    blueprint: dict[str, Any],
    epics: list[dict[str, Any]],
    sprints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    milestones: list[dict[str, Any]] = []
    roadmap = pmb.roadmap_milestones(blueprint)
    if roadmap:
        for index, milestone in enumerate(roadmap, start=1):
            week = milestone.get("week")
            title = str(milestone.get("theme") or milestone.get("name") or f"Milestone {index}")
            epic_ids = [
                epic["id"]
                for epic in epics
                if int(epic.get("week", -1)) == (int(week) if isinstance(week, (int, float)) else index)
            ]
            milestones.append(
                {
                    "id": f"MS-{index}",
                    "title": title,
                    "goal": str(milestone.get("goal") or ""),
                    "due_week": int(week) if isinstance(week, (int, float)) else index,
                    "epic_ids": epic_ids,
                }
            )
        return milestones
    for index, sprint in enumerate(sprints, start=1):
        milestones.append(
            {
                "id": f"MS-{index}",
                "title": sprint["name"],
                "goal": sprint["goal"],
                "due_week": index * 2,
                "epic_ids": [],
            }
        )
    return milestones


def _build_burndown(sprints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(sprint["total_points"] for sprint in sprints)
    count = len(sprints)
    rows: list[dict[str, Any]] = []
    for index, sprint in enumerate(sprints, start=1):
        remaining_sprints = count - index
        ideal = round(total * remaining_sprints / count) if count else 0
        rows.append(
            {
                "sprint": index,
                "name": sprint["name"],
                "points_total": sprint["total_points"],
                "points_remaining": sprint["total_points"],
                "ideal_remaining": ideal,
            }
        )
    return rows


def generate_pm(blueprint: dict[str, Any]) -> dict[str, Any]:
    info = project_info(blueprint)
    name = str(info.get("name") or "AI Blueprint Project")
    key = _project_key(name)

    epics = _build_epics(blueprint)
    _add_system_epics(blueprint, epics)
    stories = _build_stories(epics)
    epics_by_id = {epic["id"]: epic for epic in epics}

    sprints = _build_sprints(stories, epics_by_id)
    dependencies = _build_dependencies(stories, epics)
    critical_path = _critical_path(stories, dependencies)
    github_issues = _build_github_issues(stories, epics_by_id)
    jira_tasks = _build_jira_tasks(epics, stories, key)
    milestones = _build_milestones(blueprint, epics, sprints)
    burndown = _build_burndown(sprints)

    return {
        "project_name": name,
        "project_key": key,
        "epics": [
            {
                "id": epic["id"],
                "title": epic["title"],
                "description": epic["description"],
                "module": epic["module"],
                "source_sections": epic["source_sections"],
                "user_stories": [story for story in stories if story["epic_id"] == epic["id"]],
            }
            for epic in epics
        ],
        "sprint_backlog": sprints,
        "milestones": milestones,
        "dependencies": dependencies,
        "critical_path": critical_path,
        "github_issues": github_issues,
        "jira_tasks": jira_tasks,
        "sprint_burndown": burndown,
        "summary": {
            "epics": len(epics),
            "user_stories": len(stories),
            "total_points": sum(story["points"] for story in stories),
            "total_hours": sum(story["hours"] for story in stories),
            "sprints": len(sprints),
            "milestones": len(milestones),
            "github_issues": len(github_issues),
            "jira_tasks": len(jira_tasks),
            "critical_path_hours": critical_path["total_hours"],
        },
    }
