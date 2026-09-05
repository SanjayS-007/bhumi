"""check_coverage's real gate-failure reasons (kickoff §5.3), against the
real sample document's Assay run — not a synthetic CandidateFactRow
fixture, so the failed_gate/failure_reason values are whatever the real
gate pipeline actually wrote.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.assay.pipeline import run_assay
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.compute import coverage_reason
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import CandidateFactRow, DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _build(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="COVERAGE-TEST", title="t",
            publisher="CMPDI", doc_kind="sample", classification="public",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
    return engine


def test_metric_never_extracted_by_any_pack_is_not_digitised(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        reason = coverage_reason(session, "totally_unknown_metric_xyz")
    assert reason == "NOT_DIGITISED"


def test_known_metric_for_a_different_entity_is_no_source(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        known_metric = session.query(CandidateFactRow).filter(CandidateFactRow.metric_key.is_not(None)).first().metric_key
        reason = coverage_reason(session, known_metric, entity_id="ENTITY-THAT-DOES-NOT-EXIST")
    assert reason == "NO_SOURCE"


def test_soft_rejected_candidate_gives_a_real_gate_and_reason(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        rejected = session.query(CandidateFactRow).filter_by(state="soft_rejected").first()
        assert rejected is not None, "sample doc's known planted error should soft-reject at least one candidate"
        reason = coverage_reason(session, rejected.metric_key, rejected.entity_id)
    assert reason.startswith("NOT_VALIDATED:")
    assert rejected.failure_reason in reason or (rejected.failed_gate or "") in reason
