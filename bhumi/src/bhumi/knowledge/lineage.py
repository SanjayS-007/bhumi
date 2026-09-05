"""Bidirectional lineage traversal (design doc Phase 5.4). Extends
MVP-1/2's drill-down (page + bbox) so it works starting from a retrieved
passage, a published fact, a sealed BEDROCK package, or an agent answer —
not only from raw document browsing.

Forward traversal (revision-impact trace, kickoff §4.1) is now real: a
bitemporal Fact revision exists (`ledger.publish_fact`'s supersedes
chain), and package/answer lineage nodes exist (written by
`broker/server.py::seal_evidence_package` and the new `record_answer`
tool) to give it real downstream consumers to find.
"""
from __future__ import annotations

from decimal import Decimal

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


def trace_back_full(session: Session, kind: str, node_id: str) -> dict:
    """The Trace Explorer's data source (kickoff §4.3): unlike
    `trace_back()`, which follows only the first outgoing edge (correct
    for a linear fact->candidate->cell chain), this visits EVERY outgoing
    edge — needed once a node can branch, e.g. a sealed package that
    references many facts and passages. Returns {"nodes": [...],
    "edges": [...]} for direct use as a node/edge graph."""
    nodes = {(kind, node_id)}
    edges: list[dict] = []
    frontier = [(kind, node_id)]
    candidates_reached: set[str] = set()

    while frontier:
        k, i = frontier.pop()
        rows = session.execute(select(LineageEdge).where(LineageEdge.from_kind == k, LineageEdge.from_id == i)).scalars().all()
        for edge in rows:
            edges.append({"from_kind": edge.from_kind, "from_id": edge.from_id, "to_kind": edge.to_kind, "to_id": edge.to_id, "activity": edge.activity})
            if (edge.to_kind, edge.to_id) not in nodes:
                nodes.add((edge.to_kind, edge.to_id))
                if edge.to_kind == "candidate":
                    candidates_reached.add(edge.to_id)
                else:
                    frontier.append((edge.to_kind, edge.to_id))

    for cid in candidates_reached:
        row = session.get(CandidateFactRow, cid)
        if row:
            cell_id = row.source.get("cell_ref")
            nodes.add(("cell", cell_id))
            edges.append({"from_kind": "candidate", "from_id": cid, "to_kind": "cell", "to_id": cell_id, "activity": "sourced_from"})

    return {"nodes": [{"kind": k, "id": i} for k, i in nodes], "edges": edges}


def trace_forward(session: Session, kind: str, node_id: str) -> dict:
    """Given a fact/chunk/candidate, find every real downstream consumer
    that has ever pointed AT it — the reverse walk of `trace_back_full`
    (kickoff §4.1's Revision Impact Trace). A package that cited this
    fact, and any answer that cited that package, both show up here."""
    nodes = {(kind, node_id)}
    edges: list[dict] = []
    frontier = [(kind, node_id)]

    while frontier:
        k, i = frontier.pop()
        rows = session.execute(select(LineageEdge).where(LineageEdge.to_kind == k, LineageEdge.to_id == i)).scalars().all()
        for edge in rows:
            edges.append({"from_kind": edge.from_kind, "from_id": edge.from_id, "to_kind": edge.to_kind, "to_id": edge.to_id, "activity": edge.activity})
            if (edge.from_kind, edge.from_id) not in nodes:
                nodes.add((edge.from_kind, edge.from_id))
                frontier.append((edge.from_kind, edge.from_id))

    return {"nodes": [{"kind": k, "id": i} for k, i in nodes], "edges": edges}


def revision_impact(session: Session, fact: Fact, new_value: str, tolerance: str = "0.01") -> dict:
    """Classifies one hypothetical revision of `fact` as unchanged /
    immaterial / material against `tolerance`, and lists every real
    downstream consumer `trace_forward` finds — a single revision-level
    classification applied to the whole consumer set, not a per-consumer
    differential assessment (an honest simplification, not a hidden one:
    this codebase has no per-consumer tolerance semantics to differ by)."""
    consumers = trace_forward(session, "fact", fact.fact_id)
    delta = abs(Decimal(new_value) - Decimal(fact.value))
    if delta == 0:
        classification = "unchanged"
    elif delta <= Decimal(tolerance):
        classification = "immaterial"
    else:
        classification = "material"
    return {
        "fact_id": fact.fact_id, "fact_identity": fact.fact_identity,
        "old_value": str(fact.value), "new_value": str(new_value), "delta": str(delta),
        "tolerance": tolerance, "classification": classification,
        "downstream_nodes": consumers["nodes"], "downstream_edges": consumers["edges"],
    }
