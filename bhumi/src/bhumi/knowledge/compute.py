"""Minimal Compute Track (design doc's Report Engine dependency, scoped
down per this session's kickoff): looks up published fact(s) matching a
request and returns them with full provenance. No derived/formula
metrics (e.g. stripping ratio) — nothing in the current corpus needs
one, and inventing a formula to demo would be exactly the non-grounded
feature this whole system exists to avoid.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from bhumi.knowledge.ledger import current_facts
from bhumi.storage.db.models import CandidateFactRow


def compute_metric(session: Session, metric_key: str, entity_id: str | None = None, **qualifiers) -> list[dict]:
    filters = {"metric_key": metric_key}
    if entity_id:
        filters["entity_id"] = entity_id
    facts = current_facts(session, **filters)
    if qualifiers:
        facts = [f for f in facts if all(f.qualifiers.get(k) == v for k, v in qualifiers.items())]
    return [
        {
            "figure_id": f.fact_id, "metric_key": f.metric_key, "entity_id": f.entity_id,
            "value": str(f.value), "unit": f.unit, "period": f.period,
            "value_kind": f.value_kind, "qualifiers": f.qualifiers,
            "source": f.source, "confidence": f.confidence,
        }
        for f in facts
    ]


def coverage_reason(session: Session, metric_key: str, entity_id: str | None = None) -> str:
    """Why is (metric_key, entity_id) absent? (kickoff §5.3) Real reasons
    from real Assay state, not a bare boolean — the failure codes already
    exist on CandidateFactRow (`failed_gate`/`failure_reason`), they were
    just never surfaced through this tool before.

      NOT_DIGITISED  — this metric has never been extracted from ANY
                        document (no domain pack has ever emitted it)
      NO_SOURCE      — the metric is known elsewhere, but not for this
                        specific entity
      NOT_VALIDATED  — a candidate exists for this exact (metric, entity)
                        but never passed its gates; reason is the real,
                        most common (failed_gate, failure_reason) pair
    """
    any_for_metric = session.query(CandidateFactRow).filter_by(metric_key=metric_key).first()
    if any_for_metric is None:
        return "NOT_DIGITISED"

    q = session.query(CandidateFactRow).filter_by(metric_key=metric_key)
    if entity_id:
        q = q.filter_by(entity_id=entity_id)
    candidates = q.all()
    if not candidates:
        return "NO_SOURCE"

    unresolved = [c for c in candidates if c.state != "published"]
    if not unresolved:
        return "NOT_VALIDATED"  # published-but-not-current is the only way to reach here (superseded)

    reasons = Counter((c.failed_gate or "no_gate_recorded", c.failure_reason or c.state) for c in unresolved)
    top_gate, top_reason = reasons.most_common(1)[0][0]
    return f"NOT_VALIDATED: {top_gate} — {top_reason}"
