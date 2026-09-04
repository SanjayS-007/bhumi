"""The confidence-model fix (PROVENANCE.md 2026-09-05) means a clean
born-digital document no longer populates the review queue (see
test_provenance_invariant's sample-doc assertions). This test keeps the
review-queue mechanism itself exercised via a deliberately-degraded
fixture: a genuinely blank page has no text layer and no images, so the
classifier scores it below the Tier-1 floor and the router sends it
straight to review rather than fabricating an extraction."""

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import ReviewQueueItem


def test_blank_page_is_routed_to_review_not_faked(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)

    pdf_path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()  # no text, no images — genuinely unreadable by Tier 1
    doc.save(pdf_path)
    doc.close()

    with Session(engine) as session:
        ast = run_read_pipeline(session, settings, "TEST-BLANK", "test-artifact", pdf_path)
        rows = session.execute(select(ReviewQueueItem).where(ReviewQueueItem.doc_id == "TEST-BLANK")).scalars().all()

    assert not ast.texts
    assert not ast.tables
    assert len(rows) == 1
    assert rows[0].page_no == 1
