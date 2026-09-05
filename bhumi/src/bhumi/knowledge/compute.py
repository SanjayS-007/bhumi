"""Minimal Compute Track (design doc's Report Engine dependency, scoped
down per this session's kickoff): looks up published fact(s) matching a
request and returns them with full provenance. No derived/formula
metrics (e.g. stripping ratio) — nothing in the current corpus needs
one, and inventing a formula to demo would be exactly the non-grounded
feature this whole system exists to avoid.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from bhumi.knowledge.ledger import current_facts


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
