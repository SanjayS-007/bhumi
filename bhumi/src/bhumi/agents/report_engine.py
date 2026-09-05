"""Report Engine agent — a reduced but real slice (kickoff prompt §4.3).
Only imports bhumi.broker.client. Human-approval workflow is deferred —
noted as not risky to defer, per the kickoff prompt.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bhumi.broker.client import Principal, compute_metric, seal_evidence_package
from bhumi.models.backends.select import get_entailment_checker, get_narrative_generator


@dataclass
class SectionSpec:
    title: str
    metric_key: str
    entity_id: str | None = None


def generate_report(session: Session, raw_conn: sqlite3.Connection, principal: Principal, title: str, sections: list[SectionSpec]) -> dict:
    metric_keys = [s.metric_key for s in sections]
    pkg = seal_evidence_package(session, raw_conn, principal, intent=title, metric_keys=metric_keys)

    rendered_sections = []
    for spec in sections:
        coverage = pkg.coverage.get(spec.metric_key, {})
        if not coverage.get("covered"):
            rendered_sections.append({"title": spec.title, "text": f"*{spec.title}: no published data available — gap declared, not filled.*", "gap": True})
            continue
        figures = compute_metric(session, principal, spec.metric_key, spec.entity_id)
        sentences = get_narrative_generator().draft(spec.title, figures)
        evidence = [{"raw_text": f"{f['metric_key']} {f['value']} {f.get('unit', '')}"} for f in figures]
        gated_text = " ".join(
            s.text for s in sentences if get_entailment_checker().check(s.text, evidence).entailed
        )
        rendered_sections.append({"title": spec.title, "text": gated_text or f"*{spec.title}: drafted sentence failed the proof gate.*", "gap": not gated_text})

    body = f"# {title}\n\n" + "\n\n".join(f"## {s['title']}\n{s['text']}" for s in rendered_sections)
    return {"package_id": pkg.package_id, "markdown": body, "sections": rendered_sections}
