"""Fails the build if any non-blank extracted cell lacks provenance — this
is how "100% provenance" becomes a CI guarantee rather than a claim."""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from scripts.make_sample_pdf import make_sample_pdf


def _ingest_sample(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    pdf_path = tmp_path / "sample.pdf"
    make_sample_pdf(pdf_path)
    with Session(engine) as session:
        ast = run_read_pipeline(session, settings, "TEST-DOC", "test-artifact", pdf_path)
    return ast


def test_all_pages_have_bbox_capable_dimensions(tmp_path):
    ast = _ingest_sample(tmp_path)
    assert len(ast.pages) == 2
    for p in ast.pages:
        assert p.width > 0 and p.height > 0


def test_all_text_elements_have_provenance(tmp_path):
    ast = _ingest_sample(tmp_path)
    assert ast.texts
    for t in ast.texts:
        assert t.bbox is not None
        assert t.bbox.page_no == t.page_no


def test_all_nonblank_table_cells_have_bbox(tmp_path):
    ast = _ingest_sample(tmp_path)
    assert ast.tables
    for table in ast.tables:
        for cell in table.cells:
            if cell.text.strip():
                assert cell.bbox is not None, f"cell r{cell.row}c{cell.col} '{cell.text}' has no bbox"
                assert cell.bbox.page_no == table.page_no


def test_scanned_or_undecodable_pages_never_silently_extracted(tmp_path):
    """Every routing decision with tier=0 (no tier could handle it) must
    correspond to zero extracted elements on that page — no silent fake
    extraction of an unreadable page."""
    ast = _ingest_sample(tmp_path)
    no_tier_pages = {r.page_no for r in ast.routing if r.tier == 0}
    for p in no_tier_pages:
        assert not any(t.page_no == p for t in ast.texts)
        assert not any(t.page_no == p for t in ast.tables)
