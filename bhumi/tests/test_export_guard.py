"""assert_exportable is what would have prevented the restricted Marwatola
GR's content from appearing in a demo/video/public artifact by accident."""
import pytest
from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.export.guard import ExportBlocked, assert_exportable
from bhumi.schemas.core import SourceRef
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import SourceRegistry
from datetime import datetime, timezone


def _register(session: Session, artifact_id: str, classification: str) -> None:
    session.add(SourceRegistry(
        artifact_id=artifact_id, doc_id=f"D-{artifact_id}", title="t", publisher="CMPDI",
        doc_kind="geological_report", page_count=1, classification=classification,
        vault_ref="vault/x.pdf", retrieved_at=datetime.now(timezone.utc),
    ))
    session.commit()


def test_restricted_document_blocked_for_demo(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    with Session(engine) as session:
        _register(session, "restricted-1", "restricted")
        ref = SourceRef(artifact_id="restricted-1", doc_id="D", page_no=1, element_id="e")
        with pytest.raises(ExportBlocked):
            assert_exportable(session, ref, "demo")


def test_public_document_allowed_for_demo(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    with Session(engine) as session:
        _register(session, "public-1", "public")
        ref = SourceRef(artifact_id="public-1", doc_id="D", page_no=1, element_id="e")
        assert_exportable(session, ref, "demo")  # must not raise
