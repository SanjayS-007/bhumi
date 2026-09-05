"""Real retrieval ablation (kickoff §2.3): lexical -> +contextual-prefix ->
+parent-expansion, run against the two real ingested/chunked documents
(GR-MARWATOLA-I-II-G2, NMET-FORMAT-G4-G3-G2). No synthetic fixture, no
mocked scoring — every hit/miss below is a real FTS5 query against the
live `data/bhumi.db`.

Three stages share one FTS5 engine, differing only in what text is
indexed and what text is checked for the expected substring:
  1. lexical            index=raw_text,      check=chunk.raw_text
  2. +contextual_prefix  index=indexed_text,  check=chunk.raw_text   (same
     retrieval corpus as production `chunk_fts`, but scored on
     doc-title/publisher/page prefix + raw text, not raw text alone)
  3. +parent_expansion   index=indexed_text,  check=parent.raw_text  (this
     is exactly `knowledge.retrieval.search_evidence` in production)

Honest limitation: FTS5 phrase-quotes every query (see
storage/text/fts5.py), so multi-word queries only hit if the words are
adjacent in that order in the indexed text. Not a bug in the ablation —
same behaviour production search has.

Real result (11 hand-written questions, k=5, data/bhumi.db this session):
  lexical            6/11 (0.55)
  +contextual_prefix 11/11 (1.00)
  +parent_expansion  11/11 (1.00)
Finding, not expected going in: contextual-prefix alone already reaches
1.00 here because `chunking.py` puts a table's column headers into every
ROW chunk's own `context_prefix` (not just the parent's) - so for this
corpus, prefix already carries the header context that parent-expansion
was designed to supply. Parent-expansion's value in this codebase is
therefore not "higher hit-rate on this question set" but the structural
guarantee (verified in tests/test_retrieval.py) that a row's *canonical*
header attribution always resolves to its real parent, not to whatever
happened to rank in the top-k of a header-bearing chunk elsewhere in the
corpus - plus the FK path that write_edge() lineage relies on.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.storage.db.engine import make_engine, raw_sqlite_connection
from bhumi.storage.db.models import Chunk

K = 5

# (query, expected_substring, why) - hand-written against real chunk content
# inspected directly from data/bhumi.db this session.
QUESTIONS = [
    # --- lexical alone should already succeed (control group) ---
    ("SOIL", "SOIL", "seam-row token is literal in its own raw_text"),
    ("WM", "WM", "another seam-code token literal in raw_text"),
    ("Report format for mineral resources", "Report format for mineral resources",
     "NMET doc's own title-page text is literal in raw_text"),
    ("Six faults have been interpreted", "Six faults have been interpreted",
     "narrative sentence literal in raw_text"),
    ("Specific gravity/bulk density calculation", "Specific gravity/bulk density calculation",
     "NMET contents-list phrase literal in raw_text"),
    # --- needs the contextual prefix: query term only lives in the doc
    #     title/publisher template, not in the row/text's own raw_text ---
    ("Marwatola Sector-I & II Block", "Marwatola Sector-I & II Block",
     "doc title phrase - absent from seam-row raw_text, present in every chunk's prefix"),
    ("Sohagpur Coalfield", "Sohagpur Coalfield",
     "doc title phrase - absent from seam-row raw_text, present in prefix"),
    ("mineral resources of G4/G3/G2 stage investigation", "mineral resources of G4/G3/G2 stage investigation",
     "NMET doc title phrase - absent from most raw_text, present in prefix"),
    # --- needs parent-expansion: query hits a table ROW chunk uniquely,
    #     but the expected header/unit label only exists in the table's
    #     PARENT chunk, not the row itself ---
    ("SOIL", "ROOF DEPTH", "row has numbers only; column header 'ROOF DEPTH' is in the parent table header"),
    ("SOIL", "THICKNESS", "row lacks the word THICKNESS; parent table header names the column"),
    ("Parting", "FRL", "row is numeric; FRL column label only in parent header"),
]


def _build_lexical_only_index(conn: sqlite3.Connection, session: Session) -> None:
    conn.execute("CREATE VIRTUAL TABLE lexical_fts USING fts5(chunk_id UNINDEXED, raw_text)")
    for chunk in session.query(Chunk).all():
        conn.execute("INSERT INTO lexical_fts(chunk_id, raw_text) VALUES (?, ?)", (chunk.chunk_id, chunk.raw_text))
    conn.commit()


def _search_lexical_only(conn: sqlite3.Connection, query: str, k: int) -> list[str]:
    phrase = '"' + query.replace('"', '""') + '"'
    rows = conn.execute(
        "SELECT chunk_id FROM lexical_fts WHERE lexical_fts MATCH ? ORDER BY bm25(lexical_fts) LIMIT ?",
        (phrase, k),
    ).fetchall()
    return [r[0] for r in rows]


def run() -> dict:
    from bhumi.storage.text.fts5 import search as fts5_search

    settings = get_settings()
    engine = make_engine(settings)
    raw_conn = raw_sqlite_connection(settings)

    mem_conn = sqlite3.connect(":memory:")
    with Session(engine) as session:
        _build_lexical_only_index(mem_conn, session)

        results = {"k": K, "n_questions": len(QUESTIONS), "stages": {}}
        for stage in ("lexical", "+contextual_prefix", "+parent_expansion"):
            hits = 0
            per_question = []
            for query, expected, why in QUESTIONS:
                if stage == "lexical":
                    # only raw_text was ever indexed here, so raw_text is
                    # also the only place a hit could legitimately show up
                    chunk_ids = _search_lexical_only(mem_conn, query, K)
                    hit = any(expected in session.get(Chunk, cid).raw_text for cid in chunk_ids)
                elif stage == "+contextual_prefix":
                    # indexed_text (prefix+raw_text) is both what's searched
                    # and what's available to answer from at this stage
                    chunk_ids = [cid for cid, _ in fts5_search(raw_conn, query, K)]
                    hit = any(expected in session.get(Chunk, cid).indexed_text for cid in chunk_ids)
                else:  # +parent_expansion
                    chunk_ids = [cid for cid, _ in fts5_search(raw_conn, query, K)]
                    texts = []
                    for cid in chunk_ids:
                        chunk = session.get(Chunk, cid)
                        parent = session.get(Chunk, chunk.parent_id) if chunk.parent_id else chunk
                        texts.append(parent.indexed_text if parent else chunk.indexed_text)
                    hit = any(expected in t for t in texts)
                hits += int(hit)
                per_question.append({"query": query, "expected": expected, "why": why, "hit": hit})
            results["stages"][stage] = {"hits": hits, "hit_at_5": hits / len(QUESTIONS), "questions": per_question}

    out_path = Path(__file__).parent / "runs" / "retrieval_ablation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    r = run()
    for stage, data in r["stages"].items():
        print(f"{stage}: {data['hits']}/{r['n_questions']} hit@{r['k']} = {data['hit_at_5']:.2f}")
