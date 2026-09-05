"""BEDROCK TEST HARNESS — NOT THE REAL PQ DESK SERVICE.

This module exists to exercise BEDROCK's MCP tool surface with realistic
call patterns: question decomposition, evidence sealing under different
personas, coverage checks, computed figures, narrative drafting, the
Proof Gate, and provenance resolution.

It is deliberately thin. It does not represent the real PQ Desk product,
which will be designed and built as its own dedicated phase after the
data layer and BEDROCK are complete (addon 3, 2026-09-06). Do not add
product features here (Hindi output, Note for Supplementaries, annexure
export, formatting) — if a BEDROCK capability needs a new kind of test to
prove it works, add the test; don't grow this into a service. Only
imports `bhumi.broker.mcp_client`, never storage/knowledge/broker-
internals directly (enforced by tests/test_agents_use_broker_only.py) —
every BEDROCK call is a real MCP protocol round-trip over stdio to a
subprocess server, not an in-process Python function call.
"""
from __future__ import annotations

import hashlib

from bhumi.broker.mcp_client import Role, compute_metric, get_provenance, record_answer, seal_evidence_package
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

    # 6a. Provenance — real MCP round-trip, proves the figure's chain
    # resolves all the way to a real source cell/bbox, not just to a
    # fact row (kickoff addon 3 §3.1 step 7)
    provenance_chain = get_provenance("fact", figures[0]["figure_id"], role, env_overrides=env_overrides)

    # 6. Narrate
    sentences = get_narrative_generator().draft(question, figures)

    # 7. Proof Gate
    evidence = [{"raw_text": f"{f['metric_key']} {f['value']} {f.get('unit', '')}"} for f in figures]
    gated = [(s, get_entailment_checker().check(s.text, evidence)) for s in sentences]

    answer_text = " ".join(s.text for s, v in gated if v.entailed)
    # every produced answer is a lineage node too (kickoff §4.2), linked
    # to the package it consumed — enables forward trace from a fact all
    # the way to a real agent answer, not just to a sealed package
    answer_id = f"ANS-{hashlib.sha256((pkg['package_id'] + answer_text).encode()).hexdigest()[:12]}"
    record_answer(answer_id, pkg["package_id"], role, env_overrides=env_overrides)

    return {
        "package_id": pkg["package_id"], "answer_id": answer_id, "classification": classification_stub,
        "answer": answer_text,
        "figures": figures, "gap": None, "provenance_chain": provenance_chain,
    }
