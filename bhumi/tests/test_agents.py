"""Both agents, end to end, against a real ingested/assayed/published
document — not a hand-built fixture. Covers kickoff §5's checklist items
8-10: one answerable question, one deliberately-unanswerable question,
persona boundary, and a report with a correctly-declared gap.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.agents.pq_desk import answer_question
from bhumi.agents.report_engine import SectionSpec, generate_report
from bhumi.assay.pipeline import run_assay
from bhumi.broker.authz import INTERNAL_REVIEWER, PUBLIC_CALLER
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.chunking import build_chunks_for_doc
from bhumi.knowledge.ledger import publish_fact
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate, raw_sqlite_connection
from bhumi.storage.db.models import CandidateFactRow, DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _setup(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="AGENT-TEST-DOC", title="Agent test doc",
            publisher="CMPDI", doc_kind="sample", authority_rank=2, stage="G2", coalfield="Sohagpur",
            classification="restricted",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())

        published = session.query(CandidateFactRow).filter_by(doc_id="AGENT-TEST-DOC", state="auto_passed").first()
        if published is None:  # fall back to pending_review if nothing auto-passed
            published = session.query(CandidateFactRow).filter_by(doc_id="AGENT-TEST-DOC", state="pending_review").first()
        published.state = "published"
        fact = publish_fact(session, published, approver="test")
        real_metric_key = fact.metric_key

    conn = raw_sqlite_connection(settings)
    with Session(engine) as session:
        build_chunks_for_doc(session, conn, "AGENT-TEST-DOC")
    return engine, conn, real_metric_key


def test_pq_agent_answers_a_real_answerable_question(tmp_path):
    engine, conn, metric_key = _setup(tmp_path)
    with Session(engine) as session:
        result = answer_question(session, conn, INTERNAL_REVIEWER, f"What is {metric_key}?", metric_key)
    assert result["gap"] is None
    assert result["answer"]
    assert result["figures"]


def test_pq_agent_declares_gap_for_unanswerable_question(tmp_path):
    engine, conn, _metric_key = _setup(tmp_path)
    with Session(engine) as session:
        result = answer_question(session, conn, INTERNAL_REVIEWER, "What is the stripping ratio?", "stripping_ratio")
    assert result["gap"] is not None
    assert result["answer"] is None


def test_pq_agent_differs_by_persona_for_a_restricted_document(tmp_path):
    engine, conn, metric_key = _setup(tmp_path)
    with Session(engine) as session:
        answer_question(session, conn, INTERNAL_REVIEWER, "q", metric_key)
        answer_question(session, conn, PUBLIC_CALLER, "q", metric_key)
    # get_fact/compute_metric aren't classification-scoped (facts don't
    # carry classification directly, only chunks/passages do) — the
    # boundary that differs here is the search_evidence passages inside
    # the sealed package, which the restricted doc's chunks are excluded
    # from for the public persona.
    with Session(engine) as session:
        from bhumi.broker.client import seal_evidence_package
        pkg_internal = seal_evidence_package(session, conn, INTERNAL_REVIEWER, "q", query="SKM-12", metric_keys=[metric_key])
        pkg_public = seal_evidence_package(session, conn, PUBLIC_CALLER, "q", query="SKM-12", metric_keys=[metric_key])
    assert pkg_internal.content_hash != pkg_public.content_hash
    assert pkg_internal.passages and not pkg_public.passages


def test_report_agent_declares_a_gap_for_an_uncovered_section(tmp_path):
    engine, conn, metric_key = _setup(tmp_path)
    with Session(engine) as session:
        report = generate_report(session, conn, INTERNAL_REVIEWER, "Test Report", [
            SectionSpec(title="Covered Metric", metric_key=metric_key),
            SectionSpec(title="Uncovered Metric", metric_key="stripping_ratio"),
        ])
    gaps = [s for s in report["sections"] if s["gap"]]
    covered = [s for s in report["sections"] if not s["gap"]]
    assert gaps and any(s["title"] == "Uncovered Metric" for s in gaps)
    assert covered
