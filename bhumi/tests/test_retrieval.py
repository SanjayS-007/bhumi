"""Passage retrieval: real FTS5, classification filtering INSIDE the
query (design doc's explicit security property), and the backward-lineage
chain from a retrieved passage through to its source cell. Uses the real
pipeline against a synthetic document standing in for a restricted one
and the sample standing in for public, since building two full real-GR
fixtures per test would be slow; the classification VALUES used are
exactly the real ones already assigned to the Marwatola GR (restricted)
and the NMET format spec (public) in the live database.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.assay.pipeline import run_assay
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.chunking import build_chunks_for_doc
from bhumi.knowledge.lineage import trace_back
from bhumi.knowledge.retrieval import search_evidence
from bhumi.read.pipeline import run_read_pipeline
from bhumi.knowledge.ledger import publish_fact
from bhumi.storage.db.engine import migrate, raw_sqlite_connection
from bhumi.storage.db.models import CandidateFactRow, DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _ingest(tmp_path: Path, settings: Settings, doc_id: str, classification: str):
    engine = migrate(settings)
    sample_path = tmp_path / f"{doc_id}.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id=doc_id, title=f"title for {doc_id}",
            publisher="CMPDI", doc_kind="sample", authority_rank=2, stage="G2", coalfield="Sohagpur",
            classification=classification,
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
    conn = raw_sqlite_connection(settings)
    with Session(engine) as session:
        build_chunks_for_doc(session, conn, doc_id)
    return engine, conn


def test_search_finds_a_real_seam_value(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine, conn = _ingest(tmp_path, settings, "RESTRICTED-DOC", "restricted")
    with Session(engine) as session:
        results = search_evidence(session, conn, "SKM-12", k=5, max_classification=["public", "restricted"])
    assert results
    assert any("SKM-12" in r["raw_text"] or "SKM-12" in r["parent_text"] for r in results)


def test_classification_filter_excludes_restricted_for_public_persona(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine, conn = _ingest(tmp_path, settings, "RESTRICTED-DOC", "restricted")
    with Session(engine) as session:
        as_public = search_evidence(session, conn, "SKM-12", k=10, max_classification=["public"])
        as_internal = search_evidence(session, conn, "SKM-12", k=10, max_classification=["public", "restricted"])
    assert as_public == []
    assert as_internal != []


def test_search_child_returns_parent_context(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine, conn = _ingest(tmp_path, settings, "PUBLIC-DOC", "public")
    with Session(engine) as session:
        results = search_evidence(session, conn, "SKM-12", k=5, max_classification=["public"])
    assert results
    # parent_text is the whole table's header context, strictly more than the row alone
    assert len(results[0]["parent_text"]) >= len(results[0]["raw_text"])


def test_lineage_from_retrieved_passage_reaches_same_cell_as_direct_browsing(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine, conn = _ingest(tmp_path, settings, "PUBLIC-DOC", "public")
    with Session(engine) as session:
        results = search_evidence(session, conn, "SKM-12", k=5, max_classification=["public"])
        hit = next(r for r in results if r["candidate_id"])
        candidate = session.get(CandidateFactRow, hit["candidate_id"])
        candidate.entity_id = candidate.entity_id or "SKM-12"
        fact = publish_fact(session, candidate, approver="reviewer")

        chain = trace_back(session, "fact", fact.fact_id)

    kinds = [step["kind"] for step in chain]
    assert kinds[0] == "fact"
    assert "candidate" in kinds
    assert "cell" in kinds
    cell_step = chain[-1]
    # the exact same source cell direct document-browsing would show
    assert cell_step["source"]["cell_ref"] == candidate.source["cell_ref"]
