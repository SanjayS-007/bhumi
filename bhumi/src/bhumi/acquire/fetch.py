"""Fetch a document by URL and register it — the piece `register_local_file`
never had, needed for corpus.yaml-manifest-driven batch acquisition
(kickoff §3.3). Plain `requests`, no `--ssl-no-revoke` workaround needed:
that curl-specific `CRYPT_E_REVOCATION_OFFLINE` failure was a schannel/curl
quirk on this network, not present via `requests`/OpenSSL (verified this
session with a real call against nmet.gov.in).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.config.settings import Settings
from bhumi.storage.db.models import SourceRegistry


def fetch_and_register(
    session: Session, settings: Settings, url: str, doc_id: str, title: str,
    publisher: str = "OTHER", doc_kind: str = "sample", authority_rank: int = 5,
    classification: str = "public", stage: str | None = None, coalfield: str | None = None,
) -> SourceRegistry:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(resp.content)
        tmp_path = Path(f.name)
    try:
        return register_local_file(
            session, settings, tmp_path, doc_id=doc_id, title=title, publisher=publisher,
            doc_kind=doc_kind, authority_rank=authority_rank, classification=classification,
            stage=stage, coalfield=coalfield,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
