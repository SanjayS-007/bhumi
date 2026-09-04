"""Fact Ledger (Phase 5.1): bitemporal publish + the two query patterns the
design doc specifies as tested functions, not just documented SQL —
current truth and as-of. A fact is never mutated in place; `publish_fact`
either inserts the first version of a `fact_identity` or closes the prior
current version and inserts the next one.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.storage.db.models import CandidateFactRow, Fact


def fact_identity(entity_id: str, metric_key: str, qualifiers: dict, period: str, value_kind: str) -> str:
    """Deterministic across qualifier key ordering — sorted keys before
    hashing, per the design doc's explicit requirement."""
    canonical = json.dumps(qualifiers, sort_keys=True, separators=(",", ":"))
    key = f"{entity_id}|{metric_key}|{canonical}|{period}|{value_kind}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def publish_fact(session: Session, candidate: CandidateFactRow, approver: str) -> Fact:
    identity = fact_identity(candidate.entity_id, candidate.metric_key, candidate.qualifiers or {},
                              candidate.period, candidate.value_kind)
    now = datetime.now(timezone.utc)

    current = session.execute(
        select(Fact).where(Fact.fact_identity == identity, Fact.system_to.is_(None))
    ).scalar_one_or_none()

    supersedes = None
    if current is not None:
        if current.value == candidate.value and current.unit == candidate.unit:
            return current  # no real revision — republishing the same value is a no-op
        current.system_to = now
        current.valid_to = now
        supersedes = current.fact_id

    fact = Fact(
        fact_id=str(uuid.uuid4()), fact_identity=identity, entity_id=candidate.entity_id,
        metric_key=candidate.metric_key, qualifiers=candidate.qualifiers or {}, value_kind=candidate.value_kind,
        value=candidate.value, unit=candidate.unit or "", period=candidate.period, status=candidate.status or "final",
        valid_from=now, system_from=now, supersedes=supersedes,
        source=candidate.source, candidate_id=candidate.candidate_id, approver=approver,
        confidence=candidate.confidence,
    )
    session.add(fact)
    session.commit()
    return fact


def current_facts(session: Session, **filters) -> list[Fact]:
    stmt = select(Fact).where(Fact.system_to.is_(None))
    for key, value in filters.items():
        stmt = stmt.where(getattr(Fact, key) == value)
    return list(session.execute(stmt).scalars().all())


def as_of(session: Session, timestamp: datetime, **filters) -> list[Fact]:
    """What did the ledger believe at `timestamp`? — the bitemporal
    reproducibility query, as a tested function."""
    stmt = select(Fact).where(
        Fact.system_from <= timestamp,
        (Fact.system_to.is_(None)) | (Fact.system_to > timestamp),
    )
    for key, value in filters.items():
        stmt = stmt.where(getattr(Fact, key) == value)
    return list(session.execute(stmt).scalars().all())


def history(session: Session, fact_identity_value: str) -> list[Fact]:
    stmt = select(Fact).where(Fact.fact_identity == fact_identity_value).order_by(Fact.system_from)
    return list(session.execute(stmt).scalars().all())
