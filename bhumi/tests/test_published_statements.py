"""published_statement schema + honest population (kickoff §5.4), against
real published Facts from the sample document's real Assay run.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.assay.pipeline import run_assay
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.ledger import publish_fact
from bhumi.knowledge.statements import find_contradictions, populate_published_statements
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import CandidateFactRow, DocumentAst, PublishedStatement
from scripts.make_sample_pdf import make_sample_pdf


def _build(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="STMT-TEST", title="t",
            publisher="CMPDI", doc_kind="sample", classification="public",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
        published = session.query(CandidateFactRow).filter_by(doc_id="STMT-TEST", state="auto_passed").first()
        if published is None:
            published = session.query(CandidateFactRow).filter_by(doc_id="STMT-TEST", state="pending_review").first()
        published.state = "published"
        publish_fact(session, published, approver="test")
    return engine


def test_populate_creates_one_statement_per_live_fact(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        result = populate_published_statements(session)
        count = session.query(PublishedStatement).count()
    assert result["statements"] == 1
    assert count == 1


def test_populate_is_idempotent(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        populate_published_statements(session)
        populate_published_statements(session)
        count = session.query(PublishedStatement).count()
    assert count == 1  # no duplicate accumulation on re-run


def test_no_contradictions_at_this_corpus_size_is_reported_honestly(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        populate_published_statements(session)
        contradictions = find_contradictions(session)
    assert contradictions == []  # real, honest result — not faked to look used


def test_a_real_contradiction_is_detected_when_constructed(tmp_path):
    """The detector itself works — proven with two statements that
    genuinely disagree, inserted directly rather than waiting for two
    real documents to happen to overlap (none currently do, per the test
    above)."""
    engine = _build(tmp_path)
    with Session(engine) as session:
        populate_published_statements(session)
        session.add(PublishedStatement(
            statement_id="stmt-a", fact_id="fake-fact-a", doc_id="DOC-A",
            metric_key="seam_thickness_gross", entity_id="SKM-12", period="unknown",
            qualifiers={}, value="3.42", unit="m",
        ))
        session.add(PublishedStatement(
            statement_id="stmt-b", fact_id="fake-fact-b", doc_id="DOC-B",
            metric_key="seam_thickness_gross", entity_id="SKM-12", period="unknown",
            qualifiers={}, value="9.99", unit="m",
        ))
        session.commit()
        contradictions = find_contradictions(session)
    assert len(contradictions) == 1
    assert contradictions[0]["entity_id"] == "SKM-12"
