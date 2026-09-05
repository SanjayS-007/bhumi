"""Minimal BEDROCK — exactly the six tools this session's two agents need
(kickoff prompt §4.1), not the full base-design tool surface yet. Every
tool takes a Principal first and enforces classification/authz before
touching storage — this is the only place agents are allowed to reach the
knowledge layer through (see bhumi/broker/client.py and
tests/test_agents_use_broker_only.py).
"""
from __future__ import annotations

import sqlite3

from sqlalchemy.orm import Session

from bhumi.broker.authz import Principal, authorize
from bhumi.broker.package import EvidencePackage
from bhumi.knowledge.compute import compute_metric as _compute_metric
from bhumi.knowledge.ledger import current_facts
from bhumi.knowledge.lineage import trace_back
from bhumi.knowledge.retrieval import search_evidence as _search_evidence


def search_evidence(session: Session, raw_conn: sqlite3.Connection, principal: Principal, query: str, k: int = 5) -> list[dict]:
    authorize(principal, "search_evidence")
    return _search_evidence(session, raw_conn, query, k, max_classification=principal.max_classification)


def get_fact(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None) -> list[dict]:
    authorize(principal, "get_fact")
    filters = {"metric_key": metric_key}
    if entity_id:
        filters["entity_id"] = entity_id
    return [
        {"figure_id": f.fact_id, "metric_key": f.metric_key, "entity_id": f.entity_id,
         "value": str(f.value), "unit": f.unit, "confidence": f.confidence}
        for f in current_facts(session, **filters)
    ]


def compute_metric(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None, **qualifiers) -> list[dict]:
    authorize(principal, "compute_metric")
    return _compute_metric(session, metric_key, entity_id, **qualifiers)


def get_provenance(session: Session, principal: Principal, kind: str, node_id: str) -> list[dict]:
    authorize(principal, "get_provenance")
    return trace_back(session, kind, node_id)


def check_coverage(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None) -> dict:
    """Simple present/absent form (kickoff prompt §4.1) — the full
    demand-vs-provable coverage matview from Phase 6.5 does not exist."""
    authorize(principal, "check_coverage")
    figures = _compute_metric(session, metric_key, entity_id)
    return {"metric_key": metric_key, "entity_id": entity_id, "covered": bool(figures), "count": len(figures)}


def seal_evidence_package(
    session: Session, raw_conn: sqlite3.Connection, principal: Principal, intent: str, query: str | None = None,
    metric_keys: list[str] | None = None,
) -> EvidencePackage:
    authorize(principal, "seal_evidence_package")
    passages = search_evidence(session, raw_conn, principal, query, k=5) if query else []
    facts: list[dict] = []
    for mk in metric_keys or []:
        facts += get_fact(session, principal, mk)
    coverage = {mk: check_coverage(session, principal, mk) for mk in (metric_keys or [])}
    pkg = EvidencePackage(
        intent=intent, principal_subject=principal.subject, max_classification=list(principal.max_classification),
        facts=facts, passages=passages, coverage=coverage,
    )
    return pkg.seal()
