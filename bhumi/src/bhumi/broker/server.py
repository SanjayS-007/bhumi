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
from bhumi.knowledge.compute import coverage_reason as _coverage_reason
from bhumi.knowledge.ledger import current_facts
from bhumi.knowledge.lineage import revision_impact as _revision_impact
from bhumi.knowledge.lineage import trace_back, trace_back_full, write_edge
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
    """Real gate-failure reasons when absent (kickoff §5.3), not a bare
    boolean — the full demand-vs-provable coverage matview from Phase 6.5
    still does not exist, but "why" now uses real Assay state that
    already existed and was just never surfaced through this tool."""
    authorize(principal, "check_coverage")
    figures = _compute_metric(session, metric_key, entity_id)
    result = {"metric_key": metric_key, "entity_id": entity_id, "covered": bool(figures), "count": len(figures)}
    if not figures:
        result["reason"] = _coverage_reason(session, metric_key, entity_id)
    return result


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
    pkg.seal()

    # a sealed package is itself a lineage node now (kickoff §4.2), linked
    # to every fact/passage it actually consumed — this is what makes
    # trace_forward() from a fact find real packages, not just candidates
    for fact in facts:
        write_edge(session, "package", pkg.package_id, "fact", fact["figure_id"], activity="cites", agent=principal.subject)
    for passage in passages:
        write_edge(session, "package", pkg.package_id, "passage", passage["chunk_id"], activity="cites", agent=principal.subject)
    session.commit()
    return pkg


def record_answer(session: Session, principal: Principal, answer_id: str, package_id: str) -> None:
    """Every agent-produced answer/report section becomes a lineage node
    too (kickoff §4.2), linked to the sealed package(s) it consumed. The
    agent process has no direct DB access (it's a separate MCP-client
    process now) — this tool is how it registers that link without
    bypassing the broker."""
    authorize(principal, "record_answer")
    write_edge(session, "answer", answer_id, "package", package_id, activity="cites", agent=principal.subject)
    session.commit()


def get_trace_graph(session: Session, principal: Principal, kind: str, node_id: str) -> dict:
    """The Trace Explorer's data source (kickoff §4.3) — full backward
    node/edge graph from any node (answer/package/fact/passage/candidate)
    to its source cells, not just the single linear chain get_provenance
    returns."""
    authorize(principal, "get_trace_graph")
    return trace_back_full(session, kind, node_id)


def revision_impact(session: Session, principal: Principal, fact_id: str, new_value: str, tolerance: str = "0.01") -> dict:
    """kickoff §4.1's Revision Impact Trace: classify a hypothetical
    revision of a real published fact and list every real downstream
    consumer (packages, answers) — without mutating anything; this is a
    read-only what-if query, the actual revision still only ever happens
    through `ledger.publish_fact`'s supersedes chain."""
    authorize(principal, "revision_impact")
    from bhumi.storage.db.models import Fact
    fact = session.get(Fact, fact_id)
    if fact is None:
        raise ValueError(f"no such fact: {fact_id}")
    return _revision_impact(session, fact, new_value, tolerance)
