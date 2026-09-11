"""V3 sequential reasoning pipeline built with LangGraph.

Twenty agents run strictly in order: requirements, domain understanding,
business process modeling, technology evaluation, design decisions,
tradeoffs, architecture, database, API, UI/UX, security review,
performance review, scalability planning, cost estimation, business risks,
roadmap, product evolution, ADRs, testing, documentation.
Each agent receives the project input plus the structured output of every
prior agent, so later stages reason over facts established earlier.
A final Blueprint Review agent audits the assembled blueprint and
produces a quality report with consistency scores.

Every agent falls back to the deterministic reasoning engine for its own
section when the LLM is not configured or a call fails, so the pipeline
always completes and each section stays domain-aware.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.services.ai import reasoning, templates
from app.services.ai.domain_context import build_domain_context
from app.services.ai.llm import LLMClient, LLMError, LLMNotConfiguredError
from app.services.ai.prompts import AGENT_PROMPTS, VALIDATOR_PROMPT
from app.services.ai.semantic_consistency import (
    scan_section,
    semantic_consistency_review,
)

logger = logging.getLogger("ai_pipeline")
if os.getenv("BP_DEBUG"):
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

MAX_SECTION_RETRIES = 2

#: Section → model role routing for the 21 section agents plus the
#: validation agent. The role is resolved by LLMClient against configuration
#: (REASONING_PRIMARY_MODEL etc.); no model IDs live in this module.
SECTION_MODEL_ROLES: dict[str, str] = {
    "analysis": "reasoning_primary",
    "domain_understanding": "reasoning_primary",
    "business_processes": "reasoning_primary",
    "technology_selection": "coding",
    "technology_evaluation": "reasoning_secondary",
    "design_decisions": "reasoning_secondary",
    "tradeoffs": "reasoning_secondary",
    "architecture": "reasoning_primary",
    "database": "coding",
    "api": "coding",
    "ui_ux": "fast",
    "security": "reasoning_secondary",
    "performance": "reasoning_secondary",
    "scalability": "reasoning_secondary",
    "cost_estimation": "fast",
    "business_risks": "reasoning_secondary",
    "roadmap": "reasoning_secondary",
    "product_evolution": "fast",
    "adr": "fast",
    "testing": "coding",
    "documentation": "fast",
    "validation_agent": "reasoning_primary",
}


class BlueprintState(TypedDict, total=False):
    input: dict[str, Any]
    provider: str
    domain_context: dict[str, Any]
    analysis: dict[str, Any]
    domain_understanding: dict[str, Any]
    business_processes: dict[str, Any]
    technology_selection: dict[str, Any]
    technology_evaluation: dict[str, Any]
    design_decisions: dict[str, Any]
    tradeoffs: dict[str, Any]
    architecture: dict[str, Any]
    database: dict[str, Any]
    api: dict[str, Any]
    ui_ux: dict[str, Any]
    security: dict[str, Any]
    performance: dict[str, Any]
    scalability: dict[str, Any]
    cost_estimation: dict[str, Any]
    business_risks: dict[str, Any]
    roadmap: dict[str, Any]
    product_evolution: dict[str, Any]
    adr: dict[str, Any]
    testing: dict[str, Any]
    documentation: dict[str, Any]
    validation: dict[str, Any]


AGENT_KEYS = [
    "analysis",
    "domain_understanding",
    "business_processes",
    "technology_selection",
    "technology_evaluation",
    "design_decisions",
    "tradeoffs",
    "architecture",
    "database",
    "api",
    "ui_ux",
    "security",
    "performance",
    "scalability",
    "cost_estimation",
    "business_risks",
    "roadmap",
    "product_evolution",
    "adr",
    "testing",
    "documentation",
]

# Which prior sections each agent must see in its prompt (pipeline order).
CONTEXT_FOR = {
    "domain_understanding": ["analysis"],
    "business_processes": ["analysis", "domain_understanding"],
    "technology_selection": ["analysis", "domain_understanding", "business_processes"],
    "technology_evaluation": ["analysis", "domain_understanding", "business_processes", "technology_selection"],
    "design_decisions": ["analysis", "technology_selection", "technology_evaluation", "business_processes"],
    "tradeoffs": ["analysis", "technology_selection", "design_decisions", "technology_evaluation"],
    "architecture": ["analysis", "domain_understanding", "business_processes", "technology_selection", "design_decisions", "tradeoffs", "technology_evaluation"],
    "database": ["analysis", "domain_understanding", "business_processes", "technology_selection", "architecture"],
    "api": ["analysis", "domain_understanding", "business_processes", "technology_selection", "database", "architecture"],
    "ui_ux": ["analysis", "domain_understanding", "business_processes", "technology_selection", "api"],
    "security": ["analysis", "architecture", "database", "api", "technology_selection"],
    "performance": ["analysis", "database", "api", "architecture", "scalability"],
    "scalability": ["analysis", "architecture", "technology_selection", "performance"],
    "cost_estimation": ["analysis", "technology_selection", "complexity", "scalability", "security"],
    "business_risks": ["analysis", "technology_selection", "cost_estimation", "security"],
    "roadmap": ["analysis", "technology_selection", "cost_estimation", "business_risks"],
    "product_evolution": ["analysis", "roadmap", "scalability", "business_risks"],
    "adr": ["analysis", "design_decisions", "tradeoffs", "architecture", "database", "api", "security"],
    "testing": ["analysis", "api", "database", "technology_selection", "security", "performance"],
    "documentation": [
        "analysis", "domain_understanding", "business_processes", "technology_selection",
        "technology_evaluation", "design_decisions", "tradeoffs", "architecture",
        "database", "api", "ui_ux", "security", "performance", "scalability",
        "cost_estimation", "business_risks", "roadmap", "product_evolution", "adr", "testing",
    ],
}


def _build_agent_node(section: str):
    """Create a LangGraph node that produces one blueprint section.

    Each agent is wrapped in the Domain Context validation gate: after it
    produces output, the Semantic Consistency Checker scans the output against
    the forbidden vocabulary. A mismatch in a domain-aware (LLM) context is
    rejected and regenerated up to ``MAX_SECTION_RETRIES`` times before the
    section is admitted to the pipeline — it never continues with stale domain
    state from a previous generation.
    """

    def node(state: BlueprintState) -> dict[str, Any]:
        ctx = state.get("domain_context")
        project_name = (ctx or {}).get("project_name") or (state.get("input") or {}).get("name")
        domain_label = (ctx or {}).get("domain_label")
        logger.info("[%s] Input: Project=%s Domain=%s", section, project_name, domain_label)

        output = _run_agent(section, state)
        passed = True
        regen_attempts = 0
        source = "llm" if output is not None and get_settings().llm_configured else "deterministic"
        if ctx and get_settings().llm_configured:
            for _ in range(MAX_SECTION_RETRIES):
                entry = scan_section(section, {section: output}, ctx)
                if entry["status"] == "PASS":
                    break
                passed = False
                regen_attempts += 1
                logger.warning(
                    "[%s] Output domain validation FAIL — %s; regenerating.",
                    section,
                    ", ".join(entry["forbidden_terms"]) or "cross-domain mismatch",
                )
                output = _run_agent(section, state)
                if scan_section(section, {section: output}, ctx)["status"] == "PASS":
                    passed = True
                    break

            # Critical: if the LLM cannot be coerced into producing a domain-
            # consistent section after every retry, do NOT admit it — a wrong-
            # domain section would propagate through the rest of the pipeline
            # (the CityOS -> Healthcare regression). Fall back to the
            # deterministic, Domain-Context-driven generator instead.
            if not passed:
                logger.error(
                    "[%s] Failed to generate a domain-consistent section after %d retries; "
                    "falling back to the deterministic Domain-Context generator.",
                    section,
                    regen_attempts,
                )
                output = reasoning.fallback_section(section, state["input"], dict(state))
                passed = True
                source = "deterministic-fallback"

        logger.info(
            "[%s] Output: Project=%s Domain=%s Validation=%s",
            section,
            (output.get("project_name") or output.get("title") or output.get("name") or project_name),
            domain_label,
            "PASS" if passed else "FAIL",
        )
        new_debug = list(state.get("debug_report", []))
        new_debug.append(
            {
                "section": section,
                "input": {"project_name": project_name, "domain": domain_label},
                "output": {"project_name": project_name, "domain": domain_label},
                "regen_attempts": regen_attempts,
                "source": source,
                "validation": "PASS" if passed else "FAIL",
            }
        )
        return {section: output, "debug_report": new_debug}

    return node


def _run_agent(section: str, state: BlueprintState) -> dict[str, Any]:
    """Run one agent. Falls back to the deterministic reasoning engine per section."""
    project_input = state["input"]
    llm = LLMClient(model_role=SECTION_MODEL_ROLES[section])
    if llm.available:
        try:
            ctx = state.get("domain_context")
            user_prompt = f"PROJECT IDEA\n```json\n{json.dumps(project_input, indent=2)}\n```\n\n"
            if ctx:
                user_prompt += (
                    "DOMAIN CONTEXT (single source of truth — ground every decision in it)\n"
                    "```json\n"
                    f"{json.dumps(_domain_context_for_prompt(ctx), indent=2)}\n"
                    "```\n\n"
                    "RULES\n"
                    "- Use ONLY the entities, terminology and workflows from the DOMAIN CONTEXT.\n"
                    "- Never introduce business entities, modules, APIs or test names from any other industry or domain.\n"
                    f"- Forbidden vocabulary (do not use): {', '.join(ctx.get('forbidden_vocabulary', []) or []) or 'none'}.\n\n"
                )
            for ctx_key in CONTEXT_FOR.get(section, []):
                if state.get(ctx_key):
                    user_prompt += (
                        f"PREVIOUSLY DECIDED ({ctx_key})\n```json\n"
                        f"{json.dumps(state[ctx_key], indent=2)[:12000]}\n```\n\n"
                    )
            user_prompt += "Return ONLY valid JSON matching the required schema exactly."
            return llm.chat_json(AGENT_PROMPTS[section], user_prompt)
        except (LLMError, LLMNotConfiguredError):
            pass
    return reasoning.fallback_section(section, project_input, dict(state))


def _domain_context_for_prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    """Compact, prompt-friendly projection of the Domain Context."""
    return {
        "project_name": ctx.get("project_name"),
        "primary_domain": ctx.get("primary_domain"),
        "domain_label": ctx.get("domain_label"),
        "business_areas": ctx.get("business_areas", []),
        "core_entities": ctx.get("core_entities", []),
        "allowed_vocabulary": (ctx.get("allowed_vocabulary") or [])[:80],
        "forbidden_vocabulary": (ctx.get("forbidden_vocabulary") or [])[:60],
    }


def _validation_node(state: BlueprintState) -> dict[str, Any]:
    """Audit the assembled blueprint; fall back to the deterministic quality review."""
    sections = {key: state.get(key, {}) for key in AGENT_KEYS}
    blueprint_for_review = dict(sections)
    if state.get("domain_context"):
        blueprint_for_review["metadata"] = {"domain_context": state["domain_context"]}
    baseline = reasoning.validate_blueprint(blueprint_for_review)
    llm = LLMClient(model_role=SECTION_MODEL_ROLES["validation_agent"])
    if llm.available:
        try:
            user_prompt = (
                "BLUEPRINT\n```json\n"
                f"{json.dumps(sections, indent=2)[:60000]}\n```\n\n"
                "DETERMINISTIC BASELINE (keep these statuses; enrich with your findings)\n```json\n"
                f"{json.dumps(baseline, indent=2)}\n```\n"
                "Return ONLY valid JSON matching the required schema exactly."
            )
            result = llm.chat_json(VALIDATOR_PROMPT, user_prompt, max_tokens=6000)
            return {"validation": _merge_semantic_review(result, blueprint_for_review)}
        except (LLMError, LLMNotConfiguredError):
            pass
    return {"validation": baseline}


def _merge_semantic_review(validation: dict[str, Any], sections: dict[str, Any]) -> dict[str, Any]:
    """Keep the deterministic semantic consistency report on top of any LLM review."""
    semantic = semantic_consistency_review(sections)
    validation = dict(validation)
    validation["semantic_consistency"] = semantic
    quality_report = dict(validation.get("quality_report") or {})
    if semantic.get("semantic_score") is not None:
        quality_report["semantic_consistency_score"] = semantic["semantic_score"]
    validation["quality_report"] = quality_report
    return validation


def build_graph():
    """Compile the sequential LangGraph pipeline."""
    graph = StateGraph(BlueprintState)

    prev = None
    for key in AGENT_KEYS:
        name = f"{key}_agent"
        graph.add_node(name, _build_agent_node(key))
        if prev is None:
            graph.add_edge(START, name)
        else:
            graph.add_edge(prev, name)
        prev = name

    graph.add_node("validation_agent", _validation_node)
    graph.add_edge(prev, "validation_agent")
    graph.add_edge("validation_agent", END)

    return graph.compile()


def run_pipeline(project_input: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run the full pipeline. Returns (blueprint, provider_used).

    - provider == "openai" / "grok" when the LLM produced the sections.
    - provider == "template" when the deterministic reasoning engine was used
      (no key, LLM failure, or per-section fallback).

    A fresh Domain Context is built from the input for every run, so blueprint
    generations are fully isolated — no content is ever reused from a previous
    project. After assembly, the semantic consistency checker audits every
    section; failing sections are regenerated against the Domain Context.
    """
    settings = get_settings()
    provider = (settings.LLM_PROVIDER or "openai").strip().lower()
    project_input = reasoning._normalize_project_input(project_input)
    domain_context = build_domain_context(project_input)
    if settings.llm_configured:
        try:
            app = build_graph()
            state: dict[str, Any] = {
                "input": project_input,
                "provider": provider,
                "domain_context": domain_context,
            }
            final_state = app.invoke(state)
            blueprint = {key: final_state.get(key) for key in AGENT_KEYS}
            blueprint["validation"] = final_state.get("validation", {})
            debug_report = final_state.get("debug_report", [])
        except Exception as exc:  # noqa: BLE001 - surface then fall back to deterministic
            logger.exception("Agent pipeline failed (provider=%s); falling back to template engine: %s", provider, exc)
            blueprint = reasoning.generate_blueprint(project_input)
            provider = "template"
            debug_report = []
    else:
        blueprint = reasoning.generate_blueprint(project_input)
        provider = "template"
        debug_report = []

    # The deployment section is derived deterministically from the stack choice,
    # not produced by an LLM agent.
    blueprint["deployment"] = templates._deployment(project_input)

    # Domain isolation: keep the Domain Context on the blueprint so every later
    # audit (and any section regeneration) validates against the same object.
    if blueprint.get("metadata") is None:
        blueprint["metadata"] = {}
    blueprint["metadata"]["domain_context"] = domain_context
    blueprint["metadata"]["debug_report"] = _final_debug_report(blueprint, debug_report, domain_context)

    # Semantic remediation: when the LLM leaks vocabulary from another domain,
    # regenerate the flagged sections against the Domain Context and re-audit.
    blueprint = _remediate_semantics(blueprint, project_input, provider, llm_available=settings.llm_configured)
    _append_semantic_debug(blueprint, blueprint.get("validation", {}))
    return blueprint, provider


def _final_debug_report(blueprint, per_agent, ctx):
    """Aggregate per-agent validation + the post-generation semantic review."""
    semantic = semantic_consistency_review(blueprint)
    return {
        "context": {
            "project_name": ctx.get("project_name"),
            "primary_domain": ctx.get("primary_domain"),
            "domain_label": ctx.get("domain_label"),
        },
        "agents": per_agent,
        "semantic_consistency": {
            "score": semantic.get("semantic_score"),
            "skipped": semantic.get("skipped", False),
            "report": semantic.get("report", []),
        },
    }


def _append_semantic_debug(blueprint, validation):
    """Attach the semantic consistency verdict of the final review."""
    validation = validation or {}
    semantic = validation.get("semantic_consistency")
    debug = (blueprint.get("metadata") or {}).get("debug_report") or {}
    if semantic:
        debug["final_semantic_consistency"] = {
            "score": semantic.get("semantic_score"),
            "skipped": semantic.get("skipped", False),
            "report": semantic.get("report", []),
        }
        if "semantic_regenerated" in validation:
            debug["final_semantic_consistency"]["regenerated_sections"] = validation["semantic_regenerated"]
    else:
        debug["final_semantic_consistency"] = {"skipped": True}


def _remediate_semantics(
    blueprint: dict[str, Any],
    project_input: dict[str, Any],
    provider: str,
    llm_available: bool,
) -> dict[str, Any]:
    """Regenerate sections that reference vocabulary from another domain.

    Deterministic sections are already domain-driven, so no loop is needed
    there — the scan still runs as a final safety net. With the LLM, each
    flagged section is re-run once with the Domain Context in its prompt.
    """
    review = semantic_consistency_review(blueprint)
    failed = [r["section"] for r in review.get("report", []) if r["status"] == "FAIL"]
    regenerated: list[str] = []
    if failed and llm_available:
        for section in failed:
            if section not in AGENT_KEYS:
                continue
            state: dict[str, Any] = {
                "input": project_input,
                "domain_context": blueprint.get("metadata", {}).get("domain_context"),
            }
            for key in AGENT_KEYS:
                if key in blueprint:
                    state[key] = blueprint[key]
            blueprint[section] = _run_agent(section, state)
            regenerated.append(section)
    if failed or regenerated:
        sections = {key: blueprint.get(key, {}) for key in AGENT_KEYS}
        blueprint_for_review = dict(sections)
        if blueprint.get("metadata", {}).get("domain_context"):
            blueprint_for_review["metadata"] = {"domain_context": blueprint["metadata"]["domain_context"]}
        blueprint["validation"] = _validation_node({**blueprint_for_review})["validation"]
        if regenerated:
            blueprint["validation"]["semantic_regenerated"] = regenerated
    return blueprint


def regenerate_section(
    section: str, blueprint: dict[str, Any], project_input: dict[str, Any]
) -> dict[str, Any]:
    """Regenerate a single blueprint section, then re-run the Blueprint Review.

    Only the requested section is recomputed — every other section is preserved,
    so the review can flag and fix inconsistencies without rebuilding the whole
    blueprint. ``deployment`` is derived deterministically from the stack.
    """
    if section == "deployment":
        blueprint["deployment"] = templates._deployment(project_input)
    elif section in AGENT_KEYS:
        state: dict[str, Any] = {"input": project_input}
        metadata = blueprint.get("metadata") or {}
        state["domain_context"] = metadata.get("domain_context") or build_domain_context(project_input)
        for key in AGENT_KEYS:
            if key in blueprint:
                state[key] = blueprint[key]
        blueprint[section] = _run_agent(section, state)
    else:
        raise KeyError(f"Unknown blueprint section: {section}")

    sections = {key: blueprint.get(key, {}) for key in AGENT_KEYS}
    blueprint["validation"] = _validation_node(sections)["validation"]
    return blueprint
