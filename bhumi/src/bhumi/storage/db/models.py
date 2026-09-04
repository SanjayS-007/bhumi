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
