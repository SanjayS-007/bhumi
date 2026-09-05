"""FTS5 lexical text index (storage/interfaces.py::TextIndex, the sqlite
profile's implementation — real, not a stub). Runs a real FTS5 virtual
table alongside the `chunk` ORM table in the same SQLite file, using the
raw DBAPI connection since SQLAlchemy has no native FTS5 support.
"""
from __future__ import annotations

import sqlite3

_CREATE = "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_id UNINDEXED, indexed_text)"


def ensure_index(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE)


def index_chunk(conn: sqlite3.Connection, chunk_id: str, indexed_text: str) -> None:
    ensure_index(conn)
    conn.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (chunk_id,))
    conn.execute("INSERT INTO chunk_fts(chunk_id, indexed_text) VALUES (?, ?)", (chunk_id, indexed_text))


def search(conn: sqlite3.Connection, query: str, k: int) -> list[tuple[str, float]]:
    """Returns (chunk_id, rank) pairs, best first. FTS5's bm25() is
    negative-is-better; we negate so higher is better, matching every
    other ranking function in this codebase."""
    ensure_index(conn)
    # FTS5's query syntax treats bare "-" as a column-exclusion operator
    # (so "SKM-12" parses as "SKM" NOT column-12, not a literal token) —
    # quoting as a phrase makes hyphenated real-world IDs like borehole
    # numbers searchable as literal text instead of query syntax.
    phrase_query = '"' + query.replace('"', '""') + '"'
    rows = conn.execute(
        "SELECT chunk_id, bm25(chunk_fts) FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?",
        (phrase_query, k),
    ).fetchall()
    return [(chunk_id, -score) for chunk_id, score in rows]
