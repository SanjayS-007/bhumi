"""MVP-1 schema: source_registry, document_ast, page_raster, read_run,
review_queue. Dialect-neutral: plain JSON column type, no Postgres arrays,
no dialect-specific upsert (CLAUDE.md rule 6).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bhumi.storage.db.types import DecimalString


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SourceRegistry(Base):
    __tablename__ = "source_registry"

    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    publisher: Mapped[str] = mapped_column(String)
    doc_kind: Mapped[str] = mapped_column(String)
    authority_rank: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String, default="final")
    classification: Mapped[str] = mapped_column(String, default="public")
    page_count: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    coalfield: Mapped[str | None] = mapped_column(String, nullable=True)
    block: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    vault_ref: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class DocumentAst(Base):
    __tablename__ = "document_ast"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    ast_path: Mapped[str] = mapped_column(String)
    ast_hash: Mapped[str] = mapped_column(String)
    page_count: Mapped[int] = mapped_column(Integer)
    table_count: Mapped[int] = mapped_column(Integer)
    element_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PageRaster(Base):
    __tablename__ = "page_raster"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)


class ReadRun(Base):
    __tablename__ = "read_run"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    tier_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)


class CandidateFactRow(Base):
    """Phase 4 (Assay) state machine. Never hard-deleted (CLAUDE.md rule
    10) — soft_rejected candidates stay, with a reason, for re-evaluation."""

    __tablename__ = "candidate_fact"

    candidate_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    entity_raw: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metric_raw: Mapped[str] = mapped_column(String)
    metric_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    value_raw: Mapped[str] = mapped_column(String)
    value: Mapped[object | None] = mapped_column(DecimalString, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_source: Mapped[str | None] = mapped_column(String, nullable=True)
    qualifiers: Mapped[dict] = mapped_column(JSON, default=dict)
    value_kind: Mapped[str] = mapped_column(String, default="point")
    period: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[dict] = mapped_column(JSON)
    extraction_confidence: Mapped[float] = mapped_column(Float)
    domain_type: Mapped[str | None] = mapped_column(String, nullable=True)
    domain_pack_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    state: Mapped[str] = mapped_column(String, index=True, default="candidate")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    gate_results: Mapped[list] = mapped_column(JSON, default=list)
    failed_gate: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    assay_run_id: Mapped[str] = mapped_column(String, index=True)
    reeval_count: Mapped[int] = mapped_column(Integer, default=0)
    approver: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AssayRun(Base):
    __tablename__ = "assay_run"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    domain_pack_version: Mapped[int] = mapped_column(Integer)
    state_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    gate_failure_counts: Mapped[dict] = mapped_column(JSON, default=dict)


class Fact(Base):
    """Bitemporal, append-only Fact Ledger (design doc Phase 5.1). A fact
    is never updated in place — a revision closes the old row
    (system_to = now) and inserts a new one; `fact_identity` is what ties
    revisions of "the same fact" together across that history."""

    __tablename__ = "fact"

    fact_id: Mapped[str] = mapped_column(String, primary_key=True)
    fact_identity: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    metric_key: Mapped[str] = mapped_column(String, index=True)
    qualifiers: Mapped[dict] = mapped_column(JSON, default=dict)
    value_kind: Mapped[str] = mapped_column(String, default="point")
    value: Mapped[object] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String)
    period: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)

    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    system_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    system_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    supersedes: Mapped[str | None] = mapped_column(String, nullable=True)

    source: Mapped[dict] = mapped_column(JSON)
    candidate_id: Mapped[str] = mapped_column(String)
    approver: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)


class PublishedStatement(Base):
    """One row per real published Fact, denormalized by (metric_key,
    entity_id, period) across documents (design doc's contradiction-
    detection substrate, kickoff §5.4) — schema exists and is honestly
    populated from real Facts; Topic Radar's actual contradiction
    detection over this table is future work, not built this session.
    """

    __tablename__ = "published_statement"

    statement_id: Mapped[str] = mapped_column(String, primary_key=True)
    fact_id: Mapped[str] = mapped_column(String, index=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    metric_key: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String)
    qualifiers: Mapped[dict] = mapped_column(JSON, default=dict)
    value: Mapped[object] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GraphNode(Base):
    """SQL-adjacency graph (design doc Phase 5.3) — the sqlite/workstation
    profile's graph backend per storage/interfaces.py::GraphStore; no
    Apache AGE needed to be real at this scope."""

    __tablename__ = "graph_node"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, index=True)  # Coalfield|Block|Seam|Borehole|Document|Subsidiary...
    graph: Mapped[str] = mapped_column(String, index=True)  # administrative|geological|documentary
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    doc_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class GraphEdge(Base):
    __tablename__ = "graph_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src: Mapped[str] = mapped_column(String, index=True)
    dst: Mapped[str] = mapped_column(String, index=True)
    rel: Mapped[str] = mapped_column(String, index=True)
    trust_layer: Mapped[str] = mapped_column(String, default="validated")  # authoritative|validated|derived
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    fact_id: Mapped[str | None] = mapped_column(String, nullable=True)  # supporting fact, if any
    domain_pack_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doc_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class Chunk(Base):
    """Passage index (design doc Phase 5.2), scoped: parent-child from the
    AST already produced by Phase 2, real FTS5 lexical search. No vector
    stage this session — huggingface.co (and its mirror) are both
    unreachable on this network, see PROVENANCE.md 2026-09-06."""

    __tablename__ = "chunk"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer)  # 0=parent (table/section), 1=child (row/cell-group)
    raw_text: Mapped[str] = mapped_column(String)
    context_prefix: Mapped[str | None] = mapped_column(String, nullable=True)
    indexed_text: Mapped[str] = mapped_column(String)  # prefix + raw_text — what FTS5 indexes
    source: Mapped[dict] = mapped_column(JSON)
    candidate_id: Mapped[str | None] = mapped_column(String, nullable=True)  # for lineage, when exact
    classification: Mapped[str] = mapped_column(String, index=True)  # inherited from source_registry


class LineageEdge(Base):
    """Backward-traversable provenance chain, modeled loosely on W3C PROV-O
    (design doc Phase 5.4). claim/passage/fact -> candidate -> cell/element
    -> artifact. Forward (revision-impact) traversal is deliberately not
    built — no real revision history exists yet to traverse."""

    __tablename__ = "lineage_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_kind: Mapped[str] = mapped_column(String, index=True)  # claim|passage|fact|candidate|cell|element|artifact
    from_id: Mapped[str] = mapped_column(String, index=True)
    to_kind: Mapped[str] = mapped_column(String)
    to_id: Mapped[str] = mapped_column(String)
    activity: Mapped[str] = mapped_column(String)  # scan|read|type|assay|publish|retrieve
    agent: Mapped[str] = mapped_column(String, default="")
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    element_id: Mapped[str] = mapped_column(String)
    page_no: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
