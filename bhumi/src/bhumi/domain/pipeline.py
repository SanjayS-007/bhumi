"""Phase 3 orchestrator: classify every table in a document's AST, emit
candidate facts for the ones a domain pack recognises."""
from __future__ import annotations

import structlog

from bhumi.domain.classifier import classify_table, find_caption
from bhumi.domain.emit import emit_candidates
from bhumi.domain.pack import DomainPack
from bhumi.schemas.core import CandidateFact

log = structlog.get_logger()


def type_document(ast: dict, doc_id: str, artifact_id: str, pack: DomainPack) -> list[CandidateFact]:
    candidates: list[CandidateFact] = []
    for table in ast["tables"]:
        caption = find_caption(ast, table)
        result = classify_table(pack, caption, table)
        log.info(
            "table_classified",
            doc_id=doc_id, element_id=table["element_id"],
            table_type=result.table_type, confidence=result.confidence, stage=result.stage,
        )
        if result.table_type is None:
            continue
        table_type_def = pack.table_types[result.table_type]
        candidates += emit_candidates(doc_id, artifact_id, table, result.table_type, table_type_def, pack)
    return candidates
