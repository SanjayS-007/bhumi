"""Register + vault a source document (design doc Phase 1, M1.2/M1.3).
`register_before_you_parse`: a source_registry row must exist before any
read pipeline runs against a doc_id."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.storage.blob.local import LocalBlobStore
from bhumi.storage.db.models import SourceRegistry


def register_local_file(
    session: Session,
    settings: Settings,
    file_path: Path,
    doc_id: str,
    title: str,
    publisher: str = "OTHER",
    doc_kind: str = "sample",
    authority_rank: int = 5,
    status: str = "final",
    classification: str = "public",
    stage: str | None = None,
    coalfield: str | None = None,
) -> SourceRegistry:
    content = file_path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()

    vault = LocalBlobStore(settings.data_dir / "vault")
    vault_ref = vault.put(content, sha256)

    import fitz
    with fitz.open(file_path) as pdf:
        page_count = pdf.page_count

    existing = session.get(SourceRegistry, sha256)
    if existing:
        return existing

    row = SourceRegistry(
        artifact_id=sha256,
        doc_id=doc_id,
        title=title,
        publisher=publisher,
        doc_kind=doc_kind,
        authority_rank=authority_rank,
        status=status,
        classification=classification,
        page_count=page_count,
        stage=stage,
        coalfield=coalfield,
        vault_ref=vault_ref,
        retrieved_at=datetime.now(timezone.utc),
    )
    session.merge(row)
    session.commit()
    return row
