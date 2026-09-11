"""Deterministic blueprint diff engine.

Pure, order-independent JSON comparison used by the blueprint revision
system (Phase 12). It never calls an LLM and never mutates its inputs.

Diff semantics:

- Dictionaries are compared recursively by key (sorted for determinism).
- Arrays are compared as *unordered sets*: the diff reports the elements
  that were added and the elements that were removed. Reordering is not
  reported as a change because the apply pipeline replaces/merges lists
  wholesale and the V3 blueprint contract does not preserve list order
  across actions. Elements are matched by canonical JSON equality, so a
  modified object inside an array surfaces as a remove + add.
- Scalars (including ``None``) are compared with ``==``; only the
  "change" operation records before/after values.

Everything (items, groups) is emitted in sorted order so the output of
``diff_json`` for the same inputs is always identical.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

DIFF_OPS: tuple[str, str, str] = ("add", "remove", "change")

#: Human-friendly labels for common array/path leaf segments. The label is
#: chosen from the *semantics* of the segment, not its JSON type.
_LABELS: dict[str, str] = {
    "endpoints": "API endpoints",
    "tables": "database tables",
    "screens": "screens",
    "recommendations": "recommendations",
    "tasks": "tasks",
    "milestones": "milestones",
    "items": "items",
    "requirements": "requirements",
    "fields": "fields",
}


@dataclass(frozen=True)
class DiffItem:
    """One deterministic difference between two JSON values."""

    op: str
    path: tuple[str, ...]
    before: Any = field(default=None)
    after: Any = field(default=None)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _items_of(values: list[Any], op: str, path: tuple[str, ...]) -> list[DiffItem]:
    if op == "remove":
        return [DiffItem(op, path, copy.deepcopy(v), None) for v in values]
    return [DiffItem(op, path, None, copy.deepcopy(v)) for v in values]


def diff_json(
    before: Any,
    after: Any,
    path: tuple[str, ...] = (),
) -> list[DiffItem]:
    """Return a deterministic list of differences between two JSON values."""
    if isinstance(before, dict) and isinstance(after, dict):
        items: list[DiffItem] = []
        for key in sorted(set(before) | set(after)):
            child = path + (key,)
            if key not in before:
                items.append(DiffItem("add", child, None, copy.deepcopy(after[key])))
            elif key not in after:
                items.append(DiffItem("remove", child, copy.deepcopy(before[key]), None))
            else:
                items.extend(diff_json(before[key], after[key], child))
        return items

    if isinstance(before, list) and isinstance(after, list):
        before_by_key = {_canonical(v): v for v in before}
        after_by_key = {_canonical(v): v for v in after}
        removed_keys = [key for key in before_by_key if key not in after_by_key]
        added_keys = [key for key in after_by_key if key not in before_by_key]
        removed = [copy.deepcopy(before_by_key[key]) for key in removed_keys]
        added = [copy.deepcopy(after_by_key[key]) for key in added_keys]
        return _items_of(removed, "remove", path) + _items_of(added, "add", path)

    if before == after:
        return []

    return [DiffItem("change", path, copy.deepcopy(before), copy.deepcopy(after))]


def _human_segment(segment: str) -> str:
    return segment.replace("_", " ").strip()


def _label_for(path: tuple[str, ...]) -> str:
    if not path:
        return "items"
    if path == ("root",):
        return "items"
    leaf = path[-1]
    return _LABELS.get(leaf, _human_segment(leaf))


def _pluralized(label: str, count: int) -> str:
    if count == 1 and label.endswith("s"):
        return label[:-1]
    return label


def summarize_diff(items: list[DiffItem]) -> list[str]:
    """Deterministic, human-readable summary lines for a diff.

    Array/dict additions and removals are grouped by the first one or two
    path segments so related changes read as a single line (e.g. "Added 4
    API endpoints" instead of four separate lines). Scalar changes are
    counted together ("Changed 3 fields"). Lines are emitted in sorted
    group order.
    """
    if not items:
        return []

    added: dict[tuple[str, ...], int] = {}
    removed: dict[tuple[str, ...], int] = {}
    changes = 0
    for item in items:
        if item.op == "change":
            changes += 1
            continue
        key = item.path[:2] if item.path else ("root",)
        (added if item.op == "add" else removed)[key] = (
            (added if item.op == "add" else removed).get(key, 0) + 1
        )

    lines: list[str] = []
    for key in sorted(added):
        count = added[key]
        lines.append(f"Added {count} {_pluralized(_label_for(key), count)}")
    for key in sorted(removed):
        count = removed[key]
        lines.append(f"Removed {count} {_pluralized(_label_for(key), count)}")
    if changes:
        lines.append(f"Changed {changes} {_pluralized('fields', changes)}")
    return lines
