"""MVP-1 schema: source_registry, document_ast, page_raster, read_run,
review_queue. Dialect-neutral: plain JSON column type, no Postgres arrays,
no dialect-specific upsert (CLAUDE.md rule 6).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
