"""PQ Desk agent — a reduced but real slice (kickoff prompt §4.2). Only
imports bhumi.broker.mcp_client, never storage/knowledge/broker-internals
directly (enforced by tests/test_agents_use_broker_only.py) — every
BEDROCK call is a real MCP protocol round-trip over stdio to a subprocess
server, not an in-process Python function call.

Deferred, stated plainly: real classification (Starred/Unstarred/Short
Notice) is a fixed stub, not a rule/LLM call. Hindi output, annexures,
and supplementaries are not built. None of these add new architectural
risk if deferred — the point of this reduced slice is the evidence chain
and the persona boundary, not full-format PQ replies.
"""
from __future__ import annotations

from bhumi.broker.mcp_client import Role, compute_metric, seal_evidence_package
from bhumi.models.backends.select import get_entailment_checker, get_narrative_generator


def answer_question(question: str, metric_key: str, entity_id: str | None = None, *, role: Role = "internal", env_overrides: dict | None = None) -> dict:
    # 1. Classify — stubbed, deferred (see module docstring)
    classification_stub = "Starred"

    # 2. Decompose — reduced: caller supplies the metric_key directly rather
    # than an NLP decomposition step (no local/Claude/Gemini call needed
    # for this reduced slice, and inventing a fake decomposition step would
    # add complexity without adding a real capability).

    # 3. Seal + 4. Coverage — real MCP round-trip
    pkg = seal_evidence_package(question, role, metric_keys=[metric_key], env_overrides=env_overrides)
    coverage = pkg["coverage"].get(metric_key, {})

    if not coverage.get("covered"):
        return {
            "package_id": pkg["package_id"], "classification": classification_stub,
            "answer": None, "gap": f"No published fact for {metric_key}" + (f" / {entity_id}" if entity_id else ""),
        }

    # 5. Compute (already inside pkg["facts"] via seal) — real MCP round-trip
    figures = compute_metric(metric_key, role, entity_id, env_overrides=env_overrides)
    if not figures:
        return {"package_id": pkg["package_id"], "classification": classification_stub, "answer": None,
                "gap": f"metric {metric_key} covered in general but not for entity {entity_id}"}

    # 6. Narrate
    sentences = get_narrative_generator().draft(question, figures)

    # 7. Proof Gate
    evidence = [{"raw_text": f"{f['metric_key']} {f['value']} {f.get('unit', '')}"} for f in figures]
    gated = [(s, get_entailment_checker().check(s.text, evidence)) for s in sentences]

    return {
        "package_id": pkg["package_id"], "classification": classification_stub,
        "answer": " ".join(s.text for s, v in gated if v.entailed),
        "figures": figures, "gap": None,
    }
