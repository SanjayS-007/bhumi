"""BEDROCK — the evidence broker. Every tool takes a Principal first and
enforces classification/entity-scope/authz before touching storage —
this is the only place agents are allowed to reach the knowledge layer
through (see bhumi/broker/mcp_client.py and
tests/test_agents_use_broker_only.py).
"""
from __future__ import annotations

import sqlite3

from sqlalchemy.orm import Session

from bhumi.broker.authz import AccessDenied, Principal, authorize
from bhumi.broker.package import EvidencePackage
from bhumi.knowledge.compute import compute_metric as _compute_metric
from bhumi.knowledge.compute import coverage_reason as _coverage_reason
from bhumi.knowledge.ledger import current_facts
from bhumi.knowledge.lineage import revision_impact as _revision_impact
from bhumi.knowledge.lineage import trace_back, trace_back_full, write_edge
from bhumi.knowledge.retrieval import search_evidence as _search_evidence


def _in_scope(principal: Principal, doc_id: str | None) -> bool:
    """A subsidiary officer's real distinguishing scope (addon 3 §4.2) —
    None means unscoped (every other persona)."""
    return principal.entity_scope is None or doc_id is None or doc_id in principal.entity_scope


def search_evidence(session: Session, raw_conn: sqlite3.Connection, principal: Principal, query: str, k: int = 5) -> list[dict]:
    authorize(session, principal, "search_evidence")
    hits = _search_evidence(session, raw_conn, query, k * 3, max_classification=principal.max_classification)
    return [h for h in hits if _in_scope(principal, h.get("doc_id"))][:k]


def get_fact(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None) -> list[dict]:
    authorize(session, principal, "get_fact")
    filters = {"metric_key": metric_key}
    if entity_id:
        filters["entity_id"] = entity_id
    return [
        {"figure_id": f.fact_id, "metric_key": f.metric_key, "entity_id": f.entity_id,
         "value": str(f.value), "unit": f.unit, "confidence": f.confidence}
        for f in current_facts(session, **filters) if _in_scope(principal, f.source.get("doc_id"))
    ]


def compute_metric(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None, **qualifiers) -> list[dict]:
    authorize(session, principal, "compute_metric")
    figures = _compute_metric(session, metric_key, entity_id, **qualifiers)
    return [f for f in figures if _in_scope(principal, (f.get("source") or {}).get("doc_id"))]


def get_provenance(session: Session, principal: Principal, kind: str, node_id: str) -> list[dict]:
    authorize(session, principal, "get_provenance")
    return trace_back(session, kind, node_id)


def check_coverage(session: Session, principal: Principal, metric_key: str, entity_id: str | None = None) -> dict:
    """Real gate-failure reasons when absent (kickoff §5.3), not a bare
    boolean — the full demand-vs-provable coverage matview from Phase 6.5
    still does not exist, but "why" now uses real Assay state that
    already existed and was just never surfaced through this tool."""
    authorize(session, principal, "check_coverage")
    figures = compute_metric(session, principal, metric_key, entity_id)
    result = {"metric_key": metric_key, "entity_id": entity_id, "covered": bool(figures), "count": len(figures)}
    if not figures:
        result["reason"] = _coverage_reason(session, metric_key, entity_id)
    return result


def seal_evidence_package(
    session: Session, raw_conn: sqlite3.Connection, principal: Principal, intent: str, query: str | None = None,
    metric_keys: list[str] | None = None,
) -> EvidencePackage:
    authorize(session, principal, "seal_evidence_package")
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

    # persisted, not just returned (addon 3 §4.2) — this is what makes
    # replay() and merge_packages() real operations on real stored
    # content, not on whatever the caller still happens to be holding.
    # package_id IS a content hash prefix, so sealing identical content
    # twice (a real, legitimate case: e.g. the same question asked twice)
    # deterministically produces the same package_id — persisting must
    # be idempotent (check-then-skip), not a bare INSERT, or the second
    # seal of identical content raises a real sqlite3.IntegrityError
    # (UNIQUE constraint on package_id) instead of just returning the
    # same package like a content-addressed store should.
    from bhumi.storage.db.models import SealedPackage
    if session.get(SealedPackage, pkg.package_id) is None:
        session.add(SealedPackage(
            package_id=pkg.package_id, content_hash=pkg.content_hash, principal_subject=principal.subject,
            max_classification=list(principal.max_classification), body=pkg.to_dict(),
        ))
    session.commit()
    return pkg


def record_answer(session: Session, principal: Principal, answer_id: str, package_id: str) -> None:
    """Every agent-produced answer/report section becomes a lineage node
    too (kickoff §4.2), linked to the sealed package(s) it consumed. The
    agent process has no direct DB access (it's a separate MCP-client
    process now) — this tool is how it registers that link without
    bypassing the broker."""
    authorize(session, principal, "record_answer")
    write_edge(session, "answer", answer_id, "package", package_id, activity="cites", agent=principal.subject)
    session.commit()


def get_trace_graph(session: Session, principal: Principal, kind: str, node_id: str) -> dict:
    """The Trace Explorer's data source (kickoff §4.3) — full backward
    node/edge graph from any node (answer/package/fact/passage/candidate)
    to its source cells, not just the single linear chain get_provenance
    returns."""
    authorize(session, principal, "get_trace_graph")
    return trace_back_full(session, kind, node_id)


def revision_impact(session: Session, principal: Principal, fact_id: str, new_value: str, tolerance: str = "0.01") -> dict:
    """kickoff §4.1's Revision Impact Trace: classify a hypothetical
    revision of a real published fact and list every real downstream
    consumer (packages, answers) — without mutating anything; this is a
    read-only what-if query, the actual revision still only ever happens
    through `ledger.publish_fact`'s supersedes chain."""
    authorize(session, principal, "revision_impact")
    from bhumi.storage.db.models import Fact
    fact = session.get(Fact, fact_id)
    if fact is None:
        raise ValueError(f"no such fact: {fact_id}")
    return _revision_impact(session, fact, new_value, tolerance)


def list_review_queue(session: Session, principal: Principal, doc_id: str | None = None) -> list[dict]:
    """New in addon 3's full-tool-surface ask: real review-queue items
    (flagged pages/tables/failed pages), classification- and
    entity-scope-filtered exactly like every other tool — a document's
    review queue is exactly as sensitive as the document itself."""
    authorize(session, principal, "list_review_queue")
    from bhumi.storage.db.models import ReviewQueueItem, SourceRegistry

    q = session.query(ReviewQueueItem)
    if doc_id:
        q = q.filter_by(doc_id=doc_id)
    items = []
    for item in q.all():
        if not _in_scope(principal, item.doc_id):
            continue
        reg = session.query(SourceRegistry).filter_by(doc_id=item.doc_id).one_or_none()
        if reg and reg.classification not in principal.max_classification:
            continue
        items.append({
            "doc_id": item.doc_id, "element_id": item.element_id, "page_no": item.page_no,
            "reason": item.reason, "confidence": item.confidence,
        })
    return items


def list_geological_tables(session: Session, principal: Principal, doc_id: str) -> list[dict]:
    """New in addon 3's full-tool-surface ask: real table inventory for
    a document, read from its actual AST, not stubbed."""
    authorize(session, principal, "list_geological_tables")
    import json
    from bhumi.storage.db.models import DocumentAst, SourceRegistry

    reg = session.query(SourceRegistry).filter_by(doc_id=doc_id).one_or_none()
    if reg is None or reg.classification not in principal.max_classification or not _in_scope(principal, doc_id):
        return []
    ast_row = session.get(DocumentAst, doc_id)
    if ast_row is None:
        return []
    ast = json.loads(open(ast_row.ast_path, encoding="utf-8").read())
    return [{"element_id": t["element_id"], "page_no": t["page_no"], "num_cols": t.get("num_cols"),
             "num_rows": len({c["row"] for c in t["cells"]}) if t.get("cells") else 0} for t in ast.get("tables", [])]


def get_conformance_report(session: Session, principal: Principal, doc_id: str) -> dict:
    """New in addon 3's full-tool-surface ask: the real Assay gate
    breakdown for a document's most recent run — not a stub. This is the
    same `state_counts`/`gate_failure_counts` `task assay run` already
    prints, surfaced as a BEDROCK tool so an agent doesn't need shell
    access to ask "did this document pass its gates?"."""
    authorize(session, principal, "get_conformance_report")
    from bhumi.storage.db.models import AssayRun, SourceRegistry

    reg = session.query(SourceRegistry).filter_by(doc_id=doc_id).one_or_none()
    if reg is None or reg.classification not in principal.max_classification or not _in_scope(principal, doc_id):
        return {"doc_id": doc_id, "found": False}
    run = session.query(AssayRun).filter_by(doc_id=doc_id).order_by(AssayRun.started_at.desc()).first()
    if run is None:
        return {"doc_id": doc_id, "found": False}
    return {"doc_id": doc_id, "found": True, "run_id": run.run_id, "state_counts": run.state_counts,
            "gate_failure_counts": run.gate_failure_counts}


def merge_packages(session: Session, principal: Principal, package_ids: list[str], intent: str) -> dict:
    """Package composition (addon 3 §4.2): combine several ALREADY-SEALED
    packages this same principal is entitled to read into one new sealed
    package. Re-authorizes against every source package's own recorded
    `max_classification` (not just the caller's ceiling in the abstract)
    — merging must never let a caller launder access to a package
    sealed under a broader ceiling than their own."""
    authorize(session, principal, "merge_packages")
    from bhumi.storage.db.models import SealedPackage

    facts: list[dict] = []
    passages: list[dict] = []
    coverage: dict = {}
    for pid in package_ids:
        row = session.get(SealedPackage, pid)
        if row is None:
            raise ValueError(f"no such sealed package: {pid}")
        if not set(row.max_classification).issubset(set(principal.max_classification)):
            raise AccessDenied(f"{principal.subject} may not merge package {pid} (sealed under a broader classification)")
        facts += row.body.get("facts", [])
        passages += row.body.get("passages", [])
        coverage.update(row.body.get("coverage", {}))

    pkg = EvidencePackage(
        intent=intent, principal_subject=principal.subject, max_classification=list(principal.max_classification),
        facts=facts, passages=passages, coverage=coverage,
    )
    pkg.seal()
    session.add(SealedPackage(
        package_id=pkg.package_id, content_hash=pkg.content_hash, principal_subject=principal.subject,
        max_classification=list(principal.max_classification), body=pkg.to_dict(),
    ))
    for source_pid in package_ids:
        write_edge(session, "package", pkg.package_id, "package", source_pid, activity="merged_from", agent=principal.subject)
    session.commit()
    return pkg.to_dict()


def replay(session: Session, principal: Principal, package_id: str) -> dict:
    """Real replay of a previously-sealed package (addon 3 §4.2) — and
    the adversarial cache-correctness case this whole mechanism exists to
    prove: a caller may only replay a package whose recorded
    `max_classification` their OWN ceiling covers. Without this check,
    persisting packages at all would silently reopen exactly the
    unkeyed-cache leak the design doc warns about — a public caller
    replaying a restricted package's package_id by number would get the
    restricted content back. See tests/test_bedrock_hardening.py."""
    authorize(session, principal, "replay")
    from bhumi.storage.db.models import SealedPackage

    row = session.get(SealedPackage, package_id)
    if row is None:
        raise ValueError(f"no such sealed package: {package_id}")
    if not set(row.max_classification).issubset(set(principal.max_classification)):
        raise AccessDenied(f"{principal.subject} may not replay package {package_id} (sealed under a broader classification than this caller's ceiling)")
    return row.body
