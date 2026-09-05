"""Backward lineage traversal (design doc Phase 5.4). Extends MVP-1/2's
drill-down (page + bbox) so it works starting from a retrieved passage or
a published fact, not only from raw document browsing.

Forward traversal (revision-impact trace) is NOT implemented — it depends
on real revision history existing, which this corpus doesn't have yet.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.storage.db.models import CandidateFactRow, Fact, LineageEdge


def write_edge(session: Session, from_kind: str, from_id: str, to_kind: str, to_id: str,
                activity: str, agent: str = "", run_id: str | None = None) -> None:
    session.add(LineageEdge(from_kind=from_kind, from_id=from_id, to_kind=to_kind, to_id=to_id,
                             activity=activity, agent=agent, run_id=run_id))


def record_fact_lineage(session: Session, fact: Fact) -> None:
    """A fact's lineage back to its candidate is already fully determined
    by candidate_id — write it once at publish time so trace_back doesn't
    need special-case joins."""
    write_edge(session, "fact", fact.fact_id, "candidate", fact.candidate_id, activity="publish", agent=fact.approver or "")


def trace_back(session: Session, kind: str, node_id: str) -> list[dict]:
    """Walk backward from a claim/passage/fact to its source cell, using
    explicit lineage_edge rows where they exist, and falling back to the
    candidate_fact row's own source_ref for the final cell/bbox hop (that
    provenance already existed before this table did — no need to
    duplicate it into lineage_edge)."""
    chain: list[dict] = [{"kind": kind, "id": node_id}]
    current_kind, current_id = kind, node_id

    while True:
        edge = session.execute(
            select(LineageEdge).where(LineageEdge.from_kind == current_kind, LineageEdge.from_id == current_id)
        ).scalars().first()
        if not edge:
            break
        chain.append({"kind": edge.to_kind, "id": edge.to_id, "activity": edge.activity, "agent": edge.agent})
        current_kind, current_id = edge.to_kind, edge.to_id
        if current_kind == "candidate":
            break

    if current_kind == "candidate":
        row = session.get(CandidateFactRow, current_id)
        if row:
            chain.append({"kind": "cell", "id": row.source.get("cell_ref"), "source": row.source})
    return chain
