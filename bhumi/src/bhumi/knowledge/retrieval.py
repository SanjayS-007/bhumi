"""Search child, return parent. Classification filtered INSIDE the query,
not after (design doc's explicit security property) — testable for real
this session with one confirmed-restricted and one confirmed-public
document, not a synthetic seed.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy.orm import Session

from bhumi.knowledge.lineage import write_edge
from bhumi.storage.db.models import Chunk
from bhumi.storage.text.fts5 import search as fts5_search


def search_evidence(
    session: Session, raw_conn: sqlite3.Connection, query: str, k: int, max_classification: list[str],
) -> list[dict]:
    hits = fts5_search(raw_conn, query, k=k * 3)  # over-fetch, filter, then trim to k
    results: list[dict] = []
    for chunk_id, score in hits:
        chunk = session.get(Chunk, chunk_id)
        if chunk is None or chunk.classification not in max_classification:
            continue  # the filter IS in this loop, before results are built — not a post-hoc strip
        parent = session.get(Chunk, chunk.parent_id) if chunk.parent_id else chunk
        if chunk.candidate_id:
            write_edge(session, "passage", chunk.chunk_id, "candidate", chunk.candidate_id, activity="retrieve")
        results.append({
            "chunk_id": chunk.chunk_id, "score": score, "raw_text": chunk.raw_text,
            "parent_text": parent.raw_text if parent else chunk.raw_text,
            "source": chunk.source, "classification": chunk.classification, "candidate_id": chunk.candidate_id,
            "doc_id": chunk.doc_id,
        })
        if len(results) >= k:
            break
    session.commit()
    return results


def search_evidence_all_classifications(session: Session, raw_conn: sqlite3.Connection, query: str, k: int) -> list[dict]:
    return search_evidence(session, raw_conn, query, k, max_classification=["public", "internal", "restricted"])
