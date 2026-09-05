"""Chunk hierarchy + contextual prefix (design doc Phase 5.2), built from
the AST Phase 2 already produced — no new extraction. Contextual prefix
is a deterministic template, NOT LLM-generated: no local model is
fetchable on this network and no ANTHROPIC_API_KEY is configured this
session (PROVENANCE.md 2026-09-06). raw_text and indexed_text are stored
separately per the design doc's explicit rule (Topic Intelligence later
needs raw text un-polluted by the prefix).

Two-phase write, deliberately: build+commit every Chunk via the ORM
session FIRST, then index them via the raw sqlite3 connection SECOND.
Interleaving the two (one ORM session.commit() per FTS5 write) caused a
real, reproducible multi-minute "database is locked" stall — SQLite
allows only one writer, and the ORM session's open transaction blocked
the raw connection's writes for its entire uncommitted lifetime, not just
transiently. See PROVENANCE.md 2026-09-06.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bhumi.storage.db.models import CandidateFactRow, Chunk, DocumentAst, SourceRegistry


def _candidate_for_row(session: Session, doc_id: str, table_ref: str, row: int) -> str | None:
    stmt = select(CandidateFactRow.candidate_id, CandidateFactRow.source).where(
        CandidateFactRow.doc_id == doc_id
    )
    for cid, source in session.execute(stmt):
        if source.get("table_ref") == table_ref and source.get("cell_ref", "").startswith(f"r{row}c"):
            return cid
    return None


def _build_chunk_rows(session: Session, doc_id: str) -> list[Chunk]:
    reg = session.execute(select(SourceRegistry).where(SourceRegistry.doc_id == doc_id)).scalar_one()
    ast_row = session.get(DocumentAst, doc_id)
    ast = json.loads(Path(ast_row.ast_path).read_text(encoding="utf-8"))

    doc_prefix = f"Document: {reg.title}. Publisher: {reg.publisher}."
    chunks: list[Chunk] = []

    for t in ast["texts"]:
        prefix = f"{doc_prefix} Page {t['page_no']}."
        chunks.append(Chunk(
            chunk_id=f"{doc_id}:text:{t['element_id']}", doc_id=doc_id, parent_id=None, level=0,
            raw_text=t["text"], context_prefix=prefix, indexed_text=f"{prefix} {t['text']}",
            source={"page_no": t["page_no"], "bbox": t["bbox"], "element_id": t["element_id"]},
            classification=reg.classification,
        ))

    for table in ast["tables"]:
        rows_text: dict[int, list[str]] = {}
        for cell in table["cells"]:
            rows_text.setdefault(cell["row"], [None] * table["num_cols"])[cell["col"]] = cell["text"]
        header_rows = [r for r, cells in rows_text.items() if any(
            c["column_header"] for c in table["cells"] if c["row"] == r
        )]
        header_text = " ".join(t for r in sorted(header_rows) for t in (rows_text.get(r) or []) if t)

        parent_id = f"{doc_id}:table:{table['element_id']}"
        parent_prefix = f"{doc_prefix} Table on page {table['page_no']}, columns: {header_text}."
        chunks.append(Chunk(
            chunk_id=parent_id, doc_id=doc_id, parent_id=None, level=0,
            raw_text=header_text, context_prefix=parent_prefix, indexed_text=f"{parent_prefix} {header_text}",
            source={"page_no": table["page_no"], "table_ref": table["element_id"]},
            classification=reg.classification,
        ))

        for r, cells in sorted(rows_text.items()):
            if r in header_rows or not any(cells):
                continue
            row_raw = " ".join(c for c in cells if c)
            candidate_id = _candidate_for_row(session, doc_id, table["element_id"], r)
            chunks.append(Chunk(
                chunk_id=f"{doc_id}:row:{table['element_id']}:{r}", doc_id=doc_id, parent_id=parent_id, level=1,
                raw_text=row_raw, context_prefix=parent_prefix, indexed_text=f"{parent_prefix} {row_raw}",
                source={"page_no": table["page_no"], "table_ref": table["element_id"], "cell_ref": f"r{r}"},
                candidate_id=candidate_id, classification=reg.classification,
            ))

    return chunks


def build_chunks_for_doc(session: Session, raw_conn, doc_id: str) -> int:
    from bhumi.storage.text.fts5 import index_chunk  # local import: raw_conn is only needed here

    session.execute(delete(Chunk).where(Chunk.doc_id == doc_id))
    session.commit()  # release any write lock before the raw connection needs one

    chunks = _build_chunk_rows(session, doc_id)
    session.add_all(chunks)
    session.commit()  # ORM writes fully done and lock released before FTS5 writes start

    for chunk in chunks:
        index_chunk(raw_conn, chunk.chunk_id, chunk.indexed_text)
    raw_conn.commit()
    return len(chunks)
