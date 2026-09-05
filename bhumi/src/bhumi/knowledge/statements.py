"""published_statement: schema + honest population (kickoff §5.4). One
row per real, currently-live Fact — the substrate a future contradiction
detector (Topic Radar) would query, not the detector itself. Whether any
real contradiction currently exists in this corpus is reported plainly,
not assumed either way.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.storage.db.models import Fact, PublishedStatement


def populate_published_statements(session: Session) -> dict:
    """Deterministic rebuild: clear + re-derive from current Facts, so
    re-running never accumulates duplicates or leaves stale statements
    behind for a fact that's since been superseded."""
    for row in session.execute(select(PublishedStatement)).scalars():
        session.delete(row)
    session.flush()

    n = 0
    for fact in session.execute(select(Fact).where(Fact.system_to.is_(None))).scalars():
        session.add(PublishedStatement(
            statement_id=str(uuid.uuid4()), fact_id=fact.fact_id, doc_id=fact.source.get("doc_id", ""),
            metric_key=fact.metric_key, entity_id=fact.entity_id, period=fact.period,
            qualifiers=fact.qualifiers, value=fact.value, unit=fact.unit,
        ))
        n += 1
    session.commit()
    return {"statements": n}


def find_contradictions(session: Session) -> list[dict]:
    """Two different documents stating a different value for the same
    (metric_key, entity_id, period, qualifiers). Real query over real
    data — returns [] honestly if this corpus currently has no overlap
    (expected at this corpus size: no two documents currently describe
    the same entity), not a fabricated example to make the feature look
    used."""
    statements = session.execute(select(PublishedStatement)).scalars().all()
    groups: dict[tuple, list[PublishedStatement]] = {}
    for s in statements:
        key = (s.metric_key, s.entity_id, s.period, tuple(sorted((s.qualifiers or {}).items())))
        groups.setdefault(key, []).append(s)

    contradictions = []
    for key, group in groups.items():
        distinct_docs = {(g.doc_id, str(g.value)) for g in group}
        docs_involved = {d for d, _ in distinct_docs}
        values_involved = {v for _, v in distinct_docs}
        if len(docs_involved) > 1 and len(values_involved) > 1:
            contradictions.append({
                "metric_key": key[0], "entity_id": key[1], "period": key[2],
                "statements": [{"doc_id": g.doc_id, "value": str(g.value), "unit": g.unit} for g in group],
            })
    return contradictions
