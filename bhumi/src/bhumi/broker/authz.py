"""BEDROCK authorization — three personas (addon 3 §4.2's explicit ask:
"three personas, not two"): Parliament Section, CMPDI geologist, and a
subsidiary officer. The first two differ from the base two-persona model
only in name (both need full internal access — a real distinction
between them would need a role dimension this corpus has no data to back
yet, so it isn't invented). The subsidiary officer is the genuinely new
dimension: `entity_scope` restricts a principal to specific doc_ids, not
just a classification ceiling — enforced in broker/server.py's tool
wrappers, tested with a real cross-document scoping scenario in
tests/test_authz_personas.py.
"""
from __future__ import annotations

from dataclasses import dataclass

TOOLS = {
    "search_evidence", "get_fact", "compute_metric", "get_provenance", "check_coverage",
    "seal_evidence_package", "record_answer", "get_trace_graph", "revision_impact",
    "list_review_queue", "list_geological_tables", "get_conformance_report",
    "merge_packages", "replay",
}


@dataclass(frozen=True)
class Principal:
    subject: str
    max_classification: list[str]  # what this principal may ever see, e.g. ["public"]
    scopes: frozenset[str]
    entity_scope: frozenset[str] | None = None  # None = unscoped; else restricted to these doc_ids


PUBLIC_CALLER = Principal(subject="public_caller", max_classification=["public"], scopes=frozenset(TOOLS))
INTERNAL_REVIEWER = Principal(subject="internal_reviewer", max_classification=["public", "restricted"], scopes=frozenset(TOOLS))
CMPDI_GEOLOGIST = Principal(subject="cmpdi_geologist", max_classification=["public", "restricted"], scopes=frozenset(TOOLS))


def subsidiary_officer(doc_ids: list[str]) -> Principal:
    """A subsidiary officer's real distinguishing scope is which
    documents/units they may see, not a different classification
    ceiling — constructed per-subsidiary rather than a single constant,
    since the whole point is that this varies by which subsidiary."""
    return Principal(subject="subsidiary_officer", max_classification=["public", "restricted"],
                      scopes=frozenset(TOOLS), entity_scope=frozenset(doc_ids))


class AccessDenied(Exception):
    pass


def authorize(session, principal: Principal, tool: str) -> None:
    """Writes a real, queryable audit row for every decision — allowed
    or denied (addon 3 §4.2) — before raising. `session` is a plain
    SQLAlchemy Session; imported lazily here (not at module top) so
    `authz.py` stays a pure-logic module for anything that only needs
    `Principal`/`AccessDenied` and doesn't want a storage dependency."""
    from bhumi.storage.db.models import AuditLog

    allowed = tool in principal.scopes
    reason = None if allowed else f"{principal.subject} may not call {tool}"
    session.add(AuditLog(subject=principal.subject, tool=tool, allowed=allowed, reason=reason))
    session.commit()
    if not allowed:
        raise AccessDenied(reason)
