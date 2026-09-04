"""Candidate-fact emitter (design doc M3.6): table + domain type + column
mapping -> CandidateFact[], each carrying its SourceRef with the exact cell
bbox."""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

from bhumi.domain.entities import resolve_entity
from bhumi.domain.pack import DomainPack, TableTypeDef
from bhumi.domain.units import resolve_unit
from bhumi.read.headers import column_x_ranges, detect_header_row_count, resolve_headers
from bhumi.schemas.core import BBox, CandidateFact, SourceRef


def _match_column(header_chain: list[str], table_type: TableTypeDef):
    text = " ".join(header_chain).lower()
    for col in table_type.columns:
        for pat in col.match:
            if pat.lower() in text:
                return col
    return None


def emit_candidates(
    doc_id: str,
    artifact_id: str,
    table: dict,
    table_type_name: str,
    table_type: TableTypeDef,
    pack: DomainPack,
    period: str = "unknown",
) -> list[CandidateFact]:
    n_rows, n_cols = table["num_rows"], table["num_cols"]
    grid: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    bbox_grid: list[list[tuple | None]] = [[None for _ in range(n_cols)] for _ in range(n_rows)]
    cell_by_rc = {}
    for cell in table["cells"]:
        grid[cell["row"]][cell["col"]] = cell["text"]
        cell_by_rc[(cell["row"], cell["col"])] = cell
        if cell["bbox"]:
            b = cell["bbox"]
            bbox_grid[cell["row"]][cell["col"]] = (b["l"], b["t"], b["r"], b["b"])
    header_row_count = detect_header_row_count(grid)
    col_ranges = column_x_ranges(bbox_grid, n_cols)

    def _chain(c: int) -> list[str]:
        return resolve_headers(grid, header_row_count, c, cell_bboxes=bbox_grid, col_ranges=col_ranges)

    col_map = {c: (_match_column(_chain(c), table_type), _chain(c)) for c in range(n_cols)}

    candidates: list[CandidateFact] = []
    for r in range(header_row_count, n_rows):
        entity_raw_text: str = ""
        entity_val: str | None = None
        qualifiers: dict[str, str] = {}
        for c in range(n_cols):
            col, _chain = col_map[c]
            raw = grid[r][c]
            if col is None or not raw:
                continue
            if col.role == "entity":
                # entity_raw_text must survive a failed resolution — it's
                # the only thing a later pack update (assay/reeval.py) has
                # to re-attempt resolution against. Losing it here was a
                # real bug (PROVENANCE.md 2026-09-05): a soft-rejected
                # candidate with entity_raw="" can never be recovered.
                entity_raw_text = raw
                pattern = pack.entity_patterns.get(col.entity_type)
                entity_val = resolve_entity(col.entity_type, raw, pattern) if pattern else raw
            elif col.role == "qualifier":
                pattern = pack.entity_patterns.get(col.qualifier_key)
                qualifiers[col.qualifier_key] = (
                    resolve_entity(col.qualifier_key, raw, pattern) if pattern else raw
                )

        for c in range(n_cols):
            col, chain = col_map[c]
            if col is None or col.role != "metric":
                continue
            raw = grid[r][c]
            if not raw:
                continue
            cell = cell_by_rc[(r, c)]
            unit, unit_source = resolve_unit(col, chain)
            cell_qualifiers = dict(qualifiers)
            if col.stat_from_header and chain and chain[-1].lower() in ("min", "max"):
                cell_qualifiers["stat"] = chain[-1].lower()
            value = None
            if col.value_type == "decimal":
                try:
                    value = Decimal(raw)
                except InvalidOperation:
                    value = None
            cid = "cand_" + hashlib.sha256(
                f"{doc_id}-{table['element_id']}-{r}-{c}".encode()
            ).hexdigest()[:10]
            candidates.append(
                CandidateFact(
                    candidate_id=cid,
                    entity_raw=entity_raw_text,
                    entity_id=entity_val,
                    metric_raw=" > ".join(chain) if chain else "",
                    metric_key=col.metric_key,
                    value_raw=raw,
                    value=value,
                    unit=unit,
                    unit_source=unit_source,
                    qualifiers=cell_qualifiers,
                    period=period,
                    status="final",
                    source=SourceRef(
                        artifact_id=artifact_id,
                        doc_id=doc_id,
                        page_no=table["page_no"],
                        element_id=table["element_id"],
                        bbox=BBox(**cell["bbox"]) if cell["bbox"] else None,
                        table_ref=table["element_id"],
                        cell_ref=f"r{r}c{c}",
                    ),
                    extraction_confidence=table["confidence"],
                    domain_type=table_type_name,
                    domain_pack_version=pack.version,
                )
            )
    return candidates
