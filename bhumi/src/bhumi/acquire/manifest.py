"""corpus.yaml-manifest-driven batch ingestion (kickoff §3.3): reproduce
the whole real-document corpus from one command, idempotently, with one
bad document never aborting the rest of the batch (same failure-boundary
principle as read/pipeline.py's per-page resilience, one level up).
"""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.acquire.fetch import fetch_and_register
from bhumi.config.settings import Settings
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.models import DocumentAst, SourceRegistry

log = structlog.get_logger()


def _parse_page_range(pages: str | None) -> tuple[int, int] | None:
    if not pages:
        return None
    lo, hi = pages.split("-")
    return (int(lo), int(hi))


def run_manifest(session: Session, settings: Settings, manifest_path: Path) -> dict:
    entries = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))["documents"]
    results = {"ingested": [], "skipped_already_done": [], "skipped_no_source": [], "failed": []}

    for entry in entries:
        doc_id = entry["doc_id"]
        try:
            if session.get(DocumentAst, doc_id) is not None:
                results["skipped_already_done"].append(doc_id)  # idempotent: no redundant work
                continue

            reg = session.execute(select(SourceRegistry).where(SourceRegistry.doc_id == doc_id)).scalar_one_or_none()
            if reg is None:
                if not entry.get("source_url"):
                    log.warning("manifest_no_source", doc_id=doc_id, reason="not registered and no source_url — cannot reproduce from a clean data/ directory")
                    results["skipped_no_source"].append(doc_id)
                    continue
                reg = fetch_and_register(
                    session, settings, entry["source_url"], doc_id=doc_id, title=entry["title"],
                    publisher=entry.get("publisher", "OTHER"), doc_kind=entry.get("doc_kind", "sample"),
                    authority_rank=entry.get("authority_rank", 5), classification=entry.get("classification", "public"),
                    stage=entry.get("stage"), coalfield=entry.get("coalfield"),
                )

            vault_ref = Path(reg.vault_ref)
            pdf_path = vault_ref if vault_ref.is_absolute() else settings.data_dir / vault_ref
            run_read_pipeline(session, settings, reg.doc_id, reg.artifact_id, pdf_path, page_range=_parse_page_range(entry.get("page_range")))
            results["ingested"].append(doc_id)
        except Exception as e:
            # one bad document in the manifest must not abort the batch
            log.error("manifest_entry_failed", doc_id=doc_id, error=str(e))
            results["failed"].append({"doc_id": doc_id, "error": str(e)})

    return results
