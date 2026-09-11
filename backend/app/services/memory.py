"""Project memory and retrieval.

Uses ChromaDB when enabled for semantic project memory; otherwise falls back to
an in-process collection scored with simple lexical similarity. The fallback
keeps the application fully functional with zero extra dependencies.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings


class MemoryStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._chroma = None
        self._collection = None
        self._fallback_items: list[dict[str, Any]] = []
        if self.settings.CHROMA_ENABLED:
            self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self.settings.CHROMA_PATH)
            self._collection = client.get_or_create_collection("blueprint_memory")
            self._chroma = True
        except Exception:
            self._chroma = False

    def add(self, project_id: int, user_id: int, summary: str, blueprint: dict[str, Any]) -> None:
        entry = {
            "project_id": project_id,
            "user_id": user_id,
            "summary": summary,
            "category": blueprint.get("analysis", {}).get("problem_statement", "")[:200],
            "stack": blueprint.get("analysis", {}).get("technology_recommendations", []),
        }
        if self._chroma:
            try:
                self._collection.upsert(
                    ids=[str(project_id)],
                    documents=[summary],
                    metadatas=[{"user_id": user_id, "project_id": project_id}],
                )
                return
            except Exception:
                pass
        self._fallback_items.append(entry)

    def suggest(self, user_id: int, current_project_id: int | None = None, limit: int = 5) -> list[dict[str, str]]:
        """Return AI suggestions informed by previously generated blueprints."""
        items = [i for i in self._fallback_items if i["user_id"] == user_id]
        if self._chroma:
            try:
                if items:
                    results = self._collection.query(
                        query_texts=[items[-1]["summary"]],
                        n_results=min(limit, max(len(items), 1)),
                    )
                    for meta in results.get("metadatas", [[]])[0] or []:
                        for it in items:
                            if it["project_id"] == meta.get("project_id"):
                                items.append(it)
                return self._build_suggestions(items, current_project_id, limit)
            except Exception:
                pass
        return self._build_suggestions(items, current_project_id, limit)

    def _build_suggestions(
        self, items: list[dict[str, Any]], current_project_id: int | None, limit: int
    ) -> list[dict[str, str]]:
        suggestions: list[dict[str, str]] = []
        if items:
            latest = items[-1]
            suggestions.append(
                {
                    "title": "Continue where you left off",
                    "detail": f"Your most recent blueprint was for: {latest['summary'][:90]}. Open it to refine, duplicate or export.",
                    "category": "continuation",
                }
            )
            for it in items[-3:]:
                suggestions.append(
                    {
                        "title": f"Reuse the stack from '{it['summary'][:40]}'",
                        "detail": "New projects can start from a proven blueprint instead of a blank canvas.",
                        "category": "reuse",
                    }
                )
            suggestions.append(
                {
                    "title": "Add authentication & RBAC to every blueprint",
                    "detail": "Blueprints that include role-based access control ship with fewer security fixes. Keep it as a default.",
                    "category": "best_practice",
                }
            )
            suggestions.append(
                {
                    "title": "Export a blueprint to PDF for stakeholders",
                    "detail": "The export service produces professional documents — great for sign-off without sharing logins.",
                    "category": "workflow",
                }
            )
        else:
            suggestions = [
                {
                    "title": "Try an example idea",
                    "detail": "Generate a blueprint for 'Hospital Management System' to see the full output quality.",
                    "category": "onboarding",
                },
                {
                    "title": "Plan a release schedule early",
                    "detail": "Blueprints include a weekly roadmap with hour estimates — use it to set expectations with stakeholders.",
                    "category": "best_practice",
                },
                {
                    "title": "Configure an LLM API key",
                    "detail": "Without a key the app uses the built-in template engine. Add OPENAI_API_KEY for live AI generation.",
                    "category": "setup",
                },
            ]
        return suggestions[:limit]


_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
