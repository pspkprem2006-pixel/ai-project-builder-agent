"""Exporters for the project management model: Markdown, CSV and JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

EXPORT_FORMATS = ("json", "md", "csv")

ACCEPTANCE_SEPARATOR = " ; "


def to_json(model: dict[str, Any]) -> str:
    return json.dumps(model, ensure_ascii=False, indent=2)


def to_markdown(model: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = model["summary"]

    lines.append(f"# {model['project_name']} — Project Management Plan")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Epics | {summary['epics']} |")
    lines.append(f"| User stories | {summary['user_stories']} |")
    lines.append(f"| Story points | {summary['total_points']} |")
    lines.append(f"| Estimated hours | {summary['total_hours']} |")
    lines.append(f"| Sprints | {summary['sprints']} |")
    lines.append(f"| Milestones | {summary['milestones']} |")
    lines.append(f"| Critical path | {summary['critical_path_hours']} h |")
    lines.append("")
    lines.append("_Generated from the blueprint. Every task references its blueprint module(s)._")
    lines.append("")

    lines.append("## Epics & User Stories")
    for epic in model["epics"]:
        lines.append("")
        lines.append(f"### {epic['id']} — {epic['title']}")
        if epic["description"]:
            lines.append("")
            lines.append(f"> {epic['description']}")
        lines.append("")
        lines.append(
            f"_Blueprint module: `{epic['module']}` · Sections: {', '.join(epic['source_sections'])}_"
        )
        for story in epic["user_stories"]:
            lines.append("")
            lines.append(
                f"**{story['id']} — {story['title']}** "
                f"({story['points']} pts · {story['hours']} h · {story['priority']} · `{story['module']}`)"
            )
            lines.append("")
            lines.append(f"- As a {story['as_a']}, I want {story['i_want']}, so that {story['so_that']}.")
            lines.append("- Acceptance criteria:")
            for criterion in story["acceptance_criteria"]:
                lines.append(f"  - [ ] {criterion}")
    lines.append("")

    lines.append("## Sprint Backlog")
    for sprint in model["sprint_backlog"]:
        lines.append("")
        lines.append(f"### {sprint['name']}")
        lines.append("")
        lines.append(
            f"Goal: {sprint['goal']} · Points: {sprint['total_points']} · Hours: {sprint['total_hours']}"
        )
        lines.append("")
        lines.append("| Story | Title | Points | Hours | Module |")
        lines.append("| --- | --- | --- | --- | --- |")
        stories = {story["id"]: story for epic in model["epics"] for story in epic["user_stories"]}
        for story_id in sprint["story_ids"]:
            story = stories.get(story_id)
            if not story:
                continue
            lines.append(
                f"| {story['id']} | {story['title']} | {story['points']} | {story['hours']} | {story['module']} |"
            )
    lines.append("")

    lines.append("## Milestones")
    lines.append("")
    lines.append("| Milestone | Title | Due week | Epic(s) |")
    lines.append("| --- | --- | --- | --- |")
    for milestone in model["milestones"]:
        lines.append(
            f"| {milestone['id']} | {milestone['title']} | {milestone['due_week']} | "
            f"{', '.join(milestone['epic_ids']) or '—'} |"
        )
    lines.append("")

    lines.append("## Dependencies")
    lines.append("")
    for dependency in model["dependencies"]:
        lines.append(f"- `{dependency['from']}` → `{dependency['to']}` ({dependency['type']})")
    lines.append("")

    lines.append("## Critical Path")
    lines.append("")
    lines.append(" → ".join(f"`{story_id}`" for story_id in model["critical_path"]["chain"]))
    lines.append("")
    lines.append(
        f"Total: {model['critical_path']['total_hours']} h · {model['critical_path']['total_points']} points"
    )
    lines.append("")

    lines.append("## GitHub Issues")
    lines.append("")
    lines.append("| # | Title | Type | Labels |")
    lines.append("| --- | --- | --- | --- |")
    for issue in model["github_issues"]:
        lines.append(
            f"| {issue['number']} | {issue['title']} | {issue['type']} | {', '.join(issue['labels'])} |"
        )
    lines.append("")

    lines.append("## Jira Tasks")
    lines.append("")
    lines.append("| Key | Summary | Type | Points | Epic | Status |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for task in model["jira_tasks"]:
        lines.append(
            f"| {task['key']} | {task['summary']} | {task['type']} | {task['story_points']} | "
            f"{task['epic'] or '—'} | {task['status']} |"
        )
    lines.append("")

    lines.append("## Sprint Burndown (estimates)")
    lines.append("")
    lines.append("| Sprint | Name | Points total | Points remaining | Ideal remaining |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in model["sprint_burndown"]:
        lines.append(
            f"| {row['sprint']} | {row['name']} | {row['points_total']} | "
            f"{row['points_remaining']} | {row['ideal_remaining']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _story_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stories: dict[str, dict[str, Any]] = {}
    for epic in model["epics"]:
        for story in epic["user_stories"]:
            stories[story["id"]] = story
    return stories


def to_csv(model: dict[str, Any]) -> str:
    sprint_of: dict[str, int] = {}
    for sprint in model["sprint_backlog"]:
        for story_id in sprint["story_ids"]:
            sprint_of[story_id] = sprint["sprint"]
    dependency_of: dict[str, list[str]] = {}
    for edge in model["dependencies"]:
        dependency_of.setdefault(edge["from"], []).append(edge["to"])

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "title",
            "type",
            "module",
            "epic",
            "sprint",
            "points",
            "hours",
            "priority",
            "status",
            "dependencies",
            "acceptance_criteria",
            "source_sections",
        ]
    )
    for epic in model["epics"]:
        writer.writerow(
            [
                epic["id"],
                epic["title"],
                "epic",
                epic["module"],
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "; ".join(epic["source_sections"]),
            ]
        )
        for story in epic["user_stories"]:
            writer.writerow(
                [
                    story["id"],
                    story["title"],
                    "story",
                    story["module"],
                    story["epic_id"],
                    sprint_of.get(story["id"], ""),
                    story["points"],
                    story["hours"],
                    story["priority"],
                    "To Do",
                    "; ".join(dependency_of.get(story["id"], [])),
                    ACCEPTANCE_SEPARATOR.join(story["acceptance_criteria"]),
                    "; ".join(story["source_sections"]),
                ]
            )
    for task in model["jira_tasks"]:
        if task["type"] == "Chore":
            writer.writerow(
                [
                    task["key"],
                    task["summary"],
                    "chore",
                    "; ".join(task["labels"]),
                    task["epic"] or "",
                    "",
                    task["story_points"],
                    "",
                    "",
                    task["status"],
                    "",
                    "",
                    "deployment",
                ]
            )
    return buffer.getvalue()


def export(model: dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return to_json(model)
    if fmt == "md":
        return to_markdown(model)
    if fmt == "csv":
        return to_csv(model)
    raise ValueError(f"Unsupported export format '{fmt}'")
