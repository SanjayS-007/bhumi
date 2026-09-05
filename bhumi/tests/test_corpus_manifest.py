"""corpus.yaml-manifest-driven batch ingestion (kickoff §3.3). Network
calls are monkeypatched out here — fetch_and_register against a live URL
is exercised for real by hand (see PROVENANCE.md), not on every test run,
same principle as tests/conftest.py forcing the deterministic model
backend. What's tested here is the manifest's own orchestration logic:
idempotency, no-source skipping, and per-document failure isolation.
"""
import yaml
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.manifest import run_manifest
from bhumi.acquire.registry import register_local_file
from bhumi.config.settings import Settings
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _write_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "corpus.yaml"
    path.write_text(yaml.safe_dump({"documents": entries}), encoding="utf-8")
    return path


def test_manifest_skips_an_entry_with_no_source_and_not_registered(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    manifest_path = _write_manifest(tmp_path, [
        {"doc_id": "NEVER-REGISTERED", "title": "t", "source_url": None, "page_range": None},
    ])
    with Session(engine) as session:
        results = run_manifest(session, settings, manifest_path)
    assert results["skipped_no_source"] == ["NEVER-REGISTERED"]
    assert not results["ingested"]
    assert not results["failed"]


def test_manifest_ingests_an_already_registered_local_entry(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        register_local_file(session, settings, sample_path, doc_id="LOCAL-DOC", title="t", classification="public")

    manifest_path = _write_manifest(tmp_path, [
        {"doc_id": "LOCAL-DOC", "title": "t", "source_url": None, "page_range": None},
    ])
    with Session(engine) as session:
        results = run_manifest(session, settings, manifest_path)
    assert results["ingested"] == ["LOCAL-DOC"]


def test_manifest_second_run_is_idempotent(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        register_local_file(session, settings, sample_path, doc_id="LOCAL-DOC", title="t", classification="public")

    manifest_path = _write_manifest(tmp_path, [
        {"doc_id": "LOCAL-DOC", "title": "t", "source_url": None, "page_range": None},
    ])
    with Session(engine) as session:
        run_manifest(session, settings, manifest_path)
    with Session(engine) as session:
        second = run_manifest(session, settings, manifest_path)
        ast_count = session.query(DocumentAst).filter_by(doc_id="LOCAL-DOC").count()

    assert second["skipped_already_done"] == ["LOCAL-DOC"]
    assert not second["ingested"]
    assert ast_count == 1  # no redundant/duplicate work on the second run


def test_manifest_one_bad_document_does_not_abort_the_batch(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    good_path = tmp_path / "good.pdf"
    bad_path = tmp_path / "bad.pdf"
    make_sample_pdf(good_path)
    make_sample_pdf(bad_path)
    bad_path.write_bytes(bad_path.read_bytes() + b"\n%padding to force a different sha256\n")  # distinct artifact_id from good_path
    with Session(engine) as session:
        register_local_file(session, settings, good_path, doc_id="GOOD-DOC", title="t", classification="public")
        register_local_file(session, settings, bad_path, doc_id="BAD-DOC", title="t", classification="public")

    import bhumi.acquire.manifest as manifest_mod
    real_run_read_pipeline = manifest_mod.run_read_pipeline

    def faulty_run_read_pipeline(session, settings, doc_id, artifact_id, pdf_path, page_range=None):
        if doc_id == "BAD-DOC":
            raise RuntimeError("simulated bad document")
        return real_run_read_pipeline(session, settings, doc_id, artifact_id, pdf_path, page_range=page_range)

    monkeypatch.setattr(manifest_mod, "run_read_pipeline", faulty_run_read_pipeline)

    manifest_path = _write_manifest(tmp_path, [
        {"doc_id": "GOOD-DOC", "title": "t", "source_url": None, "page_range": None},
        {"doc_id": "BAD-DOC", "title": "t", "source_url": None, "page_range": None},
    ])
    with Session(engine) as session:
        results = run_manifest(session, settings, manifest_path)

    assert results["ingested"] == ["GOOD-DOC"]
    assert results["failed"] == [{"doc_id": "BAD-DOC", "error": "simulated bad document"}]
