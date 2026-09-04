"""READ pipeline orchestrator (Phase 2 end to end). classify -> route ->
raster -> tier1 extract -> normalise -> persist AST + review queue."""
from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

import structlog
from sqlalchemy import delete
from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.read.classifier import classify_page
from bhumi.read.confidence import element_confidence, table_grid_consistency
from bhumi.read.router import route_page
from bhumi.read.tiers import tier1_pymupdf
from bhumi.schemas.ast import BhumiDocument, PageInfo, RouteDecision
from bhumi.storage.db.models import DocumentAst, PageRaster, ReadRun, ReviewQueueItem

log = structlog.get_logger()


def run_read_pipeline(session: Session, settings: Settings, doc_id: str, artifact_id: str, pdf_path: Path) -> BhumiDocument:
    import fitz

    started = time.monotonic()
    doc = fitz.open(pdf_path)
    ast = BhumiDocument(doc_id=doc_id, artifact_id=artifact_id, pages=[])
    raster_root = settings.data_dir / "rasters"

    tier_counts: dict[str, int] = {}
    for page_no0, page in enumerate(doc):
        page_no = page_no0 + 1
        profile = classify_page(page, page_no)
        route = route_page(profile)
        ast.routing.append(RouteDecision(page_no=page_no, tier=route.tier or 0, reason=route.reason))

        raster_path = None
        try:
            from bhumi.read.raster import raster_page
            raster_path = str(raster_page(page, doc_id, page_no, raster_root))
        except Exception as e:  # rasterisation is best-effort, never blocks extraction
            log.warning("raster_failed", doc_id=doc_id, page_no=page_no, error=str(e))

        ast.pages.append(
            PageInfo(
                page_no=page_no,
                width=profile.width,
                height=profile.height,
                quality_score=profile.quality_score,
                text_coverage=profile.text_coverage,
                has_text_layer=profile.has_text_layer,
                is_scanned=profile.is_scanned,
                rotation=profile.rotation,
                aspect_anomaly=profile.aspect_anomaly,
                raster_path=raster_path,
            )
        )
        if raster_path:
            session.add(PageRaster(doc_id=doc_id, page_no=page_no, path=raster_path, width=profile.width, height=profile.height))

        tier_key = str(route.tier) if route.tier else "none"
        tier_counts[tier_key] = tier_counts.get(tier_key, 0) + 1

        if route.tier is None:
            session.add(
                ReviewQueueItem(
                    doc_id=doc_id,
                    element_id=f"page-{page_no}",
                    page_no=page_no,
                    reason=route.reason,
                    confidence=profile.quality_score,
                    bbox={"page_no": page_no, "l": 0, "t": 0, "r": profile.width, "b": profile.height},
                )
            )
            continue

        conf = element_confidence(profile.quality_score, route.tier)
        ast.texts += tier1_pymupdf.extract_text_elements(page, page_no, conf)
        tables = tier1_pymupdf.extract_tables(page, page_no, conf)
        for t in tables:
            grid_conf = table_grid_consistency(t.num_rows, t.num_cols, len(t.cells))
            t.confidence = element_confidence(profile.quality_score, route.tier, grid_conf)
            if t.confidence < settings.ocr_confidence_floor:
                session.add(
                    ReviewQueueItem(
                        doc_id=doc_id,
                        element_id=t.element_id,
                        page_no=page_no,
                        reason=f"table confidence {t.confidence} below floor {settings.ocr_confidence_floor}",
                        confidence=t.confidence,
                        bbox=t.bbox.model_dump(),
                    )
                )
        ast.tables += tables

    doc.close()

    ast_dir = settings.data_dir / "ast"
    ast_dir.mkdir(parents=True, exist_ok=True)
    ast_path = ast_dir / f"{doc_id}.json"
    ast_json = ast.model_dump_json(indent=2)
    ast_path.write_text(ast_json, encoding="utf-8")
    ast_hash = hashlib.sha256(ast_json.encode("utf-8")).hexdigest()

    session.execute(delete(DocumentAst).where(DocumentAst.doc_id == doc_id))
    session.add(
        DocumentAst(
            doc_id=doc_id,
            ast_path=str(ast_path),
            ast_hash=ast_hash,
            page_count=len(ast.pages),
            table_count=len(ast.tables),
            element_count=len(ast.texts) + len(ast.tables),
        )
    )
    session.add(
        ReadRun(
            run_id=str(uuid.uuid4()),
            doc_id=doc_id,
            tier_counts=tier_counts,
            duration_s=round(time.monotonic() - started, 3),
        )
    )
    session.commit()
    log.info("read_pipeline_done", doc_id=doc_id, pages=len(ast.pages), tables=len(ast.tables), tier_counts=tier_counts)
    return ast
