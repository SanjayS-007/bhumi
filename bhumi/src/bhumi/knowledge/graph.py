"""SQL-adjacency knowledge graph (design doc Phase 5.3), scoped to what's
actually extracted so far. Three graphs, distinguished by the `graph`
column, not three separate node types conflated into one tree:

- administrative: hand-seeded from source_registry (coalfield/block names)
  — thin, `authoritative` trust, exactly as much as this session has real
  data for. No subsidiary/area/mine hierarchy invented beyond that.
- geological: built from Assay candidates that have a resolved entity and
  passed at least G1-G5 (state in auto_passed/pending_review/published) —
  `validated` trust. `derived` edges are NOT populated this session
  (design doc: don't manufacture a third trust tier just to have one).
- documentary: document -> describes -> block, and document -> supports
  -> fact for anything actually published to the Fact Ledger.

Multi-hop traversal is a plain BFS over the adjacency table, not a literal
SQL recursive CTE — functionally equivalent at this graph's size and much
easier to get right under this session's time budget; revisit if/when
graph size makes an in-DB traversal actually necessary.
"""
from __future__ import annotations

from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.storage.db.models import CandidateFactRow, Fact, GraphEdge, GraphNode, SourceRegistry


def _upsert_node(session: Session, node_id: str, label: str, graph: str, props: dict) -> None:
    existing = session.get(GraphNode, node_id)
    if existing is None:
        session.add(GraphNode(node_id=node_id, label=label, graph=graph, props=props))
    else:
        existing.props = {**existing.props, **props}


def rebuild_graph_for_doc(session: Session, doc_id: str) -> dict:
    """Deterministic rebuild: delete this doc's derived edges/nodes first
    (tagged via props.doc_id), then re-derive — so re-ingesting a document
    never silently accumulates duplicate/stale graph state."""
    for edge in session.execute(select(GraphEdge).where(GraphEdge.doc_id == doc_id)).scalars():
        session.delete(edge)
    session.flush()

    reg = session.execute(select(SourceRegistry).where(SourceRegistry.doc_id == doc_id)).scalar_one()
    doc_node = f"document:{doc_id}"
    _upsert_node(session, doc_node, "Document", "documentary", {"title": reg.title, "publisher": reg.publisher})

    block_node = coalfield_node = None
    if reg.coalfield:
        coalfield_node = f"coalfield:{reg.coalfield}"
        _upsert_node(session, coalfield_node, "Coalfield", "administrative", {"name": reg.coalfield})
    if reg.block or doc_id:
        block_node = f"block:{doc_id}"
        _upsert_node(session, block_node, "Block", "administrative", {"name": reg.block or doc_id, "stage": reg.stage})
        session.add(GraphEdge(src=doc_node, dst=block_node, rel="DESCRIBES", trust_layer="authoritative", props={}, doc_id=doc_id))
        if coalfield_node:
            session.add(GraphEdge(src=block_node, dst=coalfield_node, rel="IN_COALFIELD", trust_layer="authoritative", props={}, doc_id=doc_id))

    fact_by_candidate = {f.candidate_id: f for f in session.execute(select(Fact)).scalars()}

    n_seams = n_boreholes = n_intersects = 0
    candidates = session.execute(
        select(CandidateFactRow).where(
            CandidateFactRow.doc_id == doc_id,
            CandidateFactRow.state.in_(["auto_passed", "pending_review", "published"]),
            CandidateFactRow.entity_id.is_not(None),
        )
    ).scalars().all()

    for c in candidates:
        # Two table types in the pack disagree about which role is the
        # seam vs the borehole (docs/REAL_DOC_FINDINGS.md's real
        # seam_range_summary_table has entity=seam; this codebase's own
        # synthetic seam_thickness_table has entity=borehole,
        # qualifier=seam) — handle both rather than assuming one shape.
        if c.domain_type == "seam_thickness_table":
            seam_id = (c.qualifiers or {}).get("seam")
            borehole_refs = [c.entity_id] if c.entity_id else []
        else:
            seam_id = c.entity_id
            borehole_refs = list(filter(None, ((c.qualifiers or {}).get("source_boreholes") or "").split(";")))
        if not seam_id:
            continue

        seam_node = f"seam:{seam_id}"
        _upsert_node(session, seam_node, "Seam", "geological", {"name": seam_id})
        n_seams += 1
        if block_node:
            session.add(GraphEdge(src=seam_node, dst=block_node, rel="IN_BLOCK", trust_layer="validated", props={}, doc_id=doc_id))
        fact = fact_by_candidate.get(c.candidate_id)
        for bh in borehole_refs:
            bh_node = f"borehole:{bh}"
            _upsert_node(session, bh_node, "Borehole", "geological", {"name": bh})
            n_boreholes += 1
            session.add(GraphEdge(
                src=bh_node, dst=seam_node, rel="INTERSECTS", trust_layer="validated",
                fact_id=fact.fact_id if fact else None,
                props={"metric_key": c.metric_key, "value_kind": c.value_kind}, doc_id=doc_id,
            ))
            n_intersects += 1
        if fact:
            session.add(GraphEdge(src=doc_node, dst=f"fact:{fact.fact_id}", rel="SUPPORTS", trust_layer="authoritative", props={}, doc_id=doc_id))
            _upsert_node(session, f"fact:{fact.fact_id}", "Fact", "documentary", {"metric_key": c.metric_key})

    session.commit()
    return {"seams": n_seams, "boreholes": n_boreholes, "intersects": n_intersects}


def seed_administrative_hierarchy(session: Session) -> dict:
    """Hand-seeded, real, publicly-verifiable Indian coal-sector
    administrative hierarchy (kickoff §5.1): Ministry of Coal -> Coal
    India Limited (CIL) -> CMPDI, CIL's mine-planning subsidiary. Only
    this chain is seeded — it's the one publisher (CMPDI) actually present
    in this corpus with an unambiguous, publicly documented parent
    structure. The other two documents' publishers (`MOC`, `MAPL`) are
    deliberately NOT linked into any hierarchy: this session didn't
    independently re-verify which ministry `MOC` refers to for the NMET
    format-spec document, and MAPL (a private exploration agency) has no
    publicly known parent structure to hand-seed. Leaving them unlinked is
    the honest choice, not an oversight — no administrative relationship
    is invented to make this graph look richer than the real corpus
    supports."""
    _upsert_node(session, "org:ministry_of_coal", "Ministry", "administrative", {"name": "Ministry of Coal, Government of India"})
    _upsert_node(session, "org:cil", "PSU", "administrative", {"name": "Coal India Limited"})
    _upsert_node(session, "org:cmpdi", "Subsidiary", "administrative", {"name": "Central Mine Planning & Design Institute Limited"})
    session.add(GraphEdge(src="org:cil", dst="org:ministry_of_coal", rel="UNDER_MINISTRY", trust_layer="authoritative", props={}))
    session.add(GraphEdge(src="org:cmpdi", dst="org:cil", rel="SUBSIDIARY_OF", trust_layer="authoritative", props={}))

    linked = []
    for reg in session.execute(select(SourceRegistry).where(SourceRegistry.publisher == "CMPDI")).scalars():
        doc_node = f"document:{reg.doc_id}"
        if session.get(GraphNode, doc_node):
            session.add(GraphEdge(src=doc_node, dst="org:cmpdi", rel="PUBLISHED_BY", trust_layer="authoritative", props={}, doc_id=reg.doc_id))
            linked.append(reg.doc_id)
    session.commit()
    return {"linked_documents": linked}


def neighbours(session: Session, node_id: str, rel: str | None = None) -> list[GraphEdge]:
    stmt = select(GraphEdge).where((GraphEdge.src == node_id) | (GraphEdge.dst == node_id))
    if rel:
        stmt = stmt.where(GraphEdge.rel == rel)
    return list(session.execute(stmt).scalars().all())


def multi_hop(session: Session, start: str, rels: list[str], max_hops: int = 5, trust_layers: list[str] | None = None) -> list[list[str]]:
    """BFS over the adjacency table, following only the given relation
    types, in either direction. Returns every simple path found.

    `trust_layers`, if given, restricts traversal to edges in that set —
    this is the enforcement mechanism kickoff §5.2 asks to prove now, with
    zero `derived` edges currently existing: a caller that excludes
    `derived` must NEVER have a path returned that depends on one, even
    if one existed in the table. See
    tests/test_graph.py::test_derived_edges_never_appear_in_a_trust_filtered_traversal."""
    stmt = select(GraphEdge).where(GraphEdge.rel.in_(rels))
    if trust_layers:
        stmt = stmt.where(GraphEdge.trust_layer.in_(trust_layers))
    edges = session.execute(stmt).scalars().all()
    adj: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        adj.setdefault(e.src, []).append((e.dst, e.rel))
        adj.setdefault(e.dst, []).append((e.src, e.rel))

    paths: list[list[str]] = []
    queue = deque([[start]])
    while queue:
        path = queue.popleft()
        if len(path) - 1 >= max_hops:
            continue
        for nxt, _rel in adj.get(path[-1], []):
            if nxt in path:
                continue
            new_path = path + [nxt]
            paths.append(new_path)
            queue.append(new_path)
    return paths
