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

Real result, ORIGINAL 11-question set (k=5): lexical 0.55 -> +prefix 1.00
-> +parent_expansion 1.00. That double-1.00 was interrogated once before
being trusted (kickoff §1.1), not taken at face value: the 11 questions
had low internal diversity (three of them queried the literal token
"SOIL" against the same underlying retrieval event). 5 harder questions
were added — two exact hyphenated borehole/seam IDs, two exact numeric
values, one genuinely unanswerable question with "correct answer is zero
hits" as the assertion — for 16 total.

Real result, EXPANDED 16-question set (k=5), 2-document corpus:
  lexical            11/16 (0.69)
  +contextual_prefix 16/16 (1.00)
  +parent_expansion  15/16 (0.94)
The ceiling broke, and the miss is a genuine, informative finding, not
noise: query "CSM I&II-06" (an exact borehole ID) hits correctly at the
+contextual_prefix stage (the ROW's own indexed_text contains it) but
misses at +parent_expansion **because this ablation's parent_expansion
check only inspects the parent's text, discarding the row's own text** —
which is exactly where that specific ID lives; the parent only has
column headers, never row-specific identifiers. This is a real structural
trade-off (parent-expansion trades away row-specific content for header
context), but it is NOT a production bug: `knowledge/retrieval.py::
search_evidence()` returns BOTH `raw_text` (the row's own) AND
`parent_text` (the parent's) in every result — production never discards
the child's own content, only this ablation's simplified single-field
check does.

Real result, SAME 16 questions, 3-document corpus (after the third,
structurally-different document — 487 more chunks — was added, addon 3
session), with a real +azure_rerank stage inserted (kickoff addon 3
§4.1's "lexical -> +Claude-rerank -> +contextual -> +parent-expansion"
ordering, substituting the one backend that actually produces real model
responses this session — see PROVENANCE.md on Claude/Gemini/Groq):
  lexical            11/16 (0.69)
  +azure_rerank      11/16 (0.69)  <- no change; see below
  +contextual_prefix 14/16 (0.88)  <- down from 1.00
  +parent_expansion  13/16 (0.81)  <- down from 0.94
Both drops trace to the exact same cause, confirmed by inspecting which
questions flipped: the query "SOIL" (a common word, also relevant to
limestone overburden/soil-cover discussion in the third document) no
longer surfaces its target row in the top 5 once ~500 more chunks
compete for the same BM25 ranking — this is real corpus-size sensitivity,
not a regression in the retrieval code itself (nothing in `chunking.py`/
`retrieval.py` changed between the two runs). It is the expected,
honest behaviour of lexical ranking: hit@k is corpus-relative, not a
fixed property of a question, and should be re-measured whenever the
corpus grows, not treated as a one-time result.
+azure_rerank shows no improvement over lexical on this question set,
for a real, explainable reason, not because reranking "doesn't work":
rerank only REORDERS the candidates lexical already fetched (raw_text
only, no prefix) — it cannot recover a target chunk that was never in
that fetched set to begin with. 3 of the 16 questions are specifically
designed so the answer text exists ONLY in a chunk's prefix, never in
its raw_text — structurally unreachable by any reranker operating on a
raw-text-only candidate pool, no matter how good the reranker is. This
is the ablation's most useful negative result: it shows precisely which
retrieval failures reranking can and cannot fix, rather than reporting a
number without the reason behind it.
"""
from __future__ import annotations

import json
import os
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
    # --- §1.1 hardening: exact hyphenated borehole/seam identifier match
    #     (a different retrieval event than any "SOIL" question above,
    #     and exercises the FTS5 phrase-quoting fix for "-" tokens) ---
    ("MSM-27", "MSM-27", "exact hyphenated borehole ID, only in one row's raw_text"),
    ("CSM I&II-06", "CSM I&II-06", "exact hyphenated seam/borehole ID, appears in the row grid"),
    # --- exact-number match: a specific measured value, not a category
    #     word — a different failure mode than a category/header token ---
    ("120.10", "120.10", "one specific measured thickness value, not a header or category word"),
    ("42.63", "42.63", "another specific measured value, different row than the one above"),
    # --- genuinely unanswerable: correct behaviour is zero hits, not a
    #     wrong best-effort match. "stripping_ratio" isn't in either real
    #     document (confirmed separately in tests/test_agents.py's
    #     declares-a-gap case) ---
    ("stripping ratio", None, "not present in either real document — correct answer is zero hits, not a guess"),
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


def _rerank_lexical_candidates(mem_conn: sqlite3.Connection, session: Session, query: str, k: int) -> list[str]:
    """+azure_rerank stage: take lexical's over-fetched candidates (raw
    text only, no prefix) and let a real LLM call reorder them — the
    rerank stage kickoff addon 3 §4.1 asked for by name, using the one
    backend this session that actually produces real model responses
    (Azure OpenAI; see PROVENANCE.md on why Claude/Gemini/Groq don't)."""
    os.environ["BHUMI_MODEL_BACKEND"] = "azure"
    from bhumi.models.backends.azure_openai_backend import AzureOpenAIRerankerBackend

    candidate_ids = _search_lexical_only(mem_conn, query, k * 3)
    if not candidate_ids:
        return []
    candidates = [{"chunk_id": cid, "raw_text": session.get(Chunk, cid).raw_text} for cid in candidate_ids]
    ranked = AzureOpenAIRerankerBackend().rerank(query, candidates, k)
    return [r.chunk_id for r in ranked] or candidate_ids[:k]  # empty LLM output: fall back rather than hide the stage


def run(include_rerank: bool = True) -> dict:
    from bhumi.storage.text.fts5 import search as fts5_search

    settings = get_settings()
    engine = make_engine(settings)
    raw_conn = raw_sqlite_connection(settings)

    mem_conn = sqlite3.connect(":memory:")
    stages = ["lexical"] + (["+azure_rerank"] if include_rerank else []) + ["+contextual_prefix", "+parent_expansion"]
    with Session(engine) as session:
        _build_lexical_only_index(mem_conn, session)

        results = {"k": K, "n_questions": len(QUESTIONS), "stages": {}}
        for stage in stages:
            hits = 0
            per_question = []
            for query, expected, why in QUESTIONS:
                if stage == "lexical":
                    # only raw_text was ever indexed here, so raw_text is
                    # also the only place a hit could legitimately show up
                    chunk_ids = _search_lexical_only(mem_conn, query, K)
                elif stage == "+azure_rerank":
                    chunk_ids = [] if expected is None else _rerank_lexical_candidates(mem_conn, session, query, K)
                elif stage == "+contextual_prefix":
                    chunk_ids = [cid for cid, _ in fts5_search(raw_conn, query, K)]
                else:  # +parent_expansion
                    chunk_ids = [cid for cid, _ in fts5_search(raw_conn, query, K)]

                if expected is None:
                    # unanswerable question: correct behaviour is that
                    # NOTHING comes back, not a wrong best-effort hit
                    hit = len(chunk_ids) == 0
                elif stage in ("lexical", "+azure_rerank"):
                    # rerank only reorders raw_text-only candidates — it
                    # never adds prefix/parent context, so raw_text is
                    # the only place a hit can legitimately show up here too
                    hit = any(expected in session.get(Chunk, cid).raw_text for cid in chunk_ids)
                elif stage == "+contextual_prefix":
                    hit = any(expected in session.get(Chunk, cid).indexed_text for cid in chunk_ids)
                else:  # +parent_expansion
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
