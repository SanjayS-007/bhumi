"""BEDROCK TEST HARNESS — NOT THE REAL REPORT ENGINE SERVICE.

This module exists to exercise BEDROCK's MCP tool surface against a
different real consumption shape than pq_client.py: multi-section,
multi-call evidence gathering (seal a package once, per-section coverage
checks, per-section compute+narrate+gate) rather than a single question.

It is deliberately thin. It does not represent the real Report Engine
product, which will be designed and built as its own dedicated phase
after the data layer and BEDROCK are complete (addon 3, 2026-09-06). Do
not add product features here (a human-approval/freezing workflow reusing
the Assay review pattern, derived/formula metrics, DOCX/PDF export) — that
belongs to the real service's own design session. Only imports
`bhumi.broker.mcp_client`, never storage/knowledge/broker-internals
directly (enforced by tests/test_agents_use_broker_only.py).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from bhumi.broker.mcp_client import Role, compute_metric, record_answer, seal_evidence_package
from bhumi.models.backends.select import get_entailment_checker, get_narrative_generator


@dataclass
class SectionSpec:
    title: str
    metric_key: str
    entity_id: str | None = None


def generate_report(title: str, sections: list[SectionSpec], *, role: Role = "internal", env_overrides: dict | None = None) -> dict:
    metric_keys = [s.metric_key for s in sections]
    pkg = seal_evidence_package(title, role, metric_keys=metric_keys, env_overrides=env_overrides)

    rendered_sections = []
    for spec in sections:
        coverage = pkg["coverage"].get(spec.metric_key, {})
        if not coverage.get("covered"):
            rendered_sections.append({"title": spec.title, "text": f"*{spec.title}: no published data available — gap declared, not filled.*", "gap": True, "answer_id": None})
            continue
        figures = compute_metric(spec.metric_key, role, spec.entity_id, env_overrides=env_overrides)
        sentences = get_narrative_generator().draft(spec.title, figures)
        evidence = [{"raw_text": f"{f['metric_key']} {f['value']} {f.get('unit', '')}"} for f in figures]
        gated_text = " ".join(
            s.text for s in sentences if get_entailment_checker().check(s.text, evidence).entailed
        )
        section_text = gated_text or f"*{spec.title}: drafted sentence failed the proof gate.*"
        section_id = None
        if gated_text:
            # a covered, gate-passed section is a lineage node too (§4.2)
            # — a declared gap has no evidence to link, so no node is
            # written for it (nothing to trace forward from)
            section_id = f"ANS-{hashlib.sha256((pkg['package_id'] + section_text).encode()).hexdigest()[:12]}"
            record_answer(section_id, pkg["package_id"], role, env_overrides=env_overrides)
        rendered_sections.append({"title": spec.title, "text": section_text, "gap": not gated_text, "answer_id": section_id})

    body = f"# {title}\n\n" + "\n\n".join(f"## {s['title']}\n{s['text']}" for s in rendered_sections)
    return {"package_id": pkg["package_id"], "markdown": body, "sections": rendered_sections}
