"""Partial-failure resilience (kickoff §3.2): one malformed page must not
abort the whole document's read pipeline. Faults a real page via
monkeypatch (constructing an organically-malformed PDF page is fragile
and not the point being tested) and asserts the OTHER page still ingests
cleanly while the bad one is visibly flagged, not silently dropped or
fatal.
"""

import bhumi.read.pipeline as pipeline_mod
from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.config.settings import Settings
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import ReviewQueueItem
from scripts.make_sample_pdf import make_sample_pdf


def test_one_bad_page_does_not_abort_the_rest_of_the_document(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)  # a real 2-page PDF

    real_classify = pipeline_mod.classify_page

    def faulty_classify(page, page_no):
        if page_no == 1:
            raise RuntimeError("simulated malformed page")
        return real_classify(page, page_no)

    monkeypatch.setattr(pipeline_mod, "classify_page", faulty_classify)

    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="RESILIENCE-TEST-DOC", title="t",
            publisher="TEST", doc_kind="sample", classification="public",
        )
        ast = run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)

        # page 1 (the faulty one) never made it into ast.pages; page 2 did
        assert [p.page_no for p in ast.pages] == [2]

        failed_items = session.query(ReviewQueueItem).filter_by(doc_id="RESILIENCE-TEST-DOC").filter(
            ReviewQueueItem.element_id.like("%-failed")
        ).all()
        assert len(failed_items) == 1
        assert failed_items[0].page_no == 1
        assert "simulated malformed page" in failed_items[0].reason
