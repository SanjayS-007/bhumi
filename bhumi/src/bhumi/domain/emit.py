"""Candidate-fact emitter (design doc M3.6): table + domain type + column
mapping -> CandidateFact[], each carrying its SourceRef with the exact cell
bbox.

Row groups (docs/REAL_DOC_FINDINGS.md #9, diagnosed 2026-09-06): a real
seam's values row is sometimes followed by a borehole-reference row whose
identity columns are blank. Before this fix, that continuation row was
treated as an independent data row — its metric-column cells (which hold
borehole ID *strings*, not measurements) became spurious candidates that
only happened to soft-reject because the entity column was blank. Now:
detected via the `blank_continuation` signal and merged into the owning
row's `source_boreholes` qualifier instead of emitting garbage candidates.
"""
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


def _is_identity_column(col) -> bool:
    return col is not None and col.role in ("entity", "qualifier")


def _extract_borehole_refs(row: list[str], pack: DomainPack) -> list[str]:
    pattern = pack.entity_patterns.get("borehole")
    if not pattern:
        return []
    refs = []
    for cell in row:
        if not cell:
            continue
        resolved = resolve_entity("borehole", cell, pattern)
        if resolved:
            refs.append(resolved)
    return refs


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
    identity_cols = [c for c, (col, _) in col_map.items() if _is_identity_column(col)]

    def _identity_blank(r: int) -> bool:
        return identity_cols and all(not grid[r][c].strip() for c in identity_cols)

    candidates: list[CandidateFact] = []
    row_group_boreholes: dict[int, list[str]] = {}  # owning row -> refs found in its continuation row(s)
    owning_row: int | None = None

    for r in range(header_row_count, n_rows):
        if not any(cell.strip() for cell in grid[r]):
            continue  # fully blank spacer row
        if _identity_blank(r) and owning_row is not None:
            # blank_continuation signal: not a new record, a continuation
            # of the previous one (design doc's RowGroup, minimal form).
            refs = _extract_borehole_refs(grid[r], pack)
            if refs:
                row_group_boreholes.setdefault(owning_row, []).extend(refs)
            continue
        owning_row = r

    for r in range(header_row_count, n_rows):
        if _identity_blank(r):
            continue  # continuation row — already folded into its owner above, emits nothing itself
        if not any(cell.strip() for cell in grid[r]):
            continue

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

        source_boreholes = row_group_boreholes.get(r)
        if source_boreholes:
            qualifiers["source_boreholes"] = ";".join(sorted(set(source_boreholes)))

        for c in range(n_cols):
            col, chain = col_map[c]
            if col is None or col.role != "metric":
                continue
            raw = grid[r][c]
            if not raw:
                continue
            cell = cell_by_rc[(r, c)]
            unit, unit_source = resolve_unit(col, chain)
            value_kind = "point"
            if col.stat_from_header and chain and chain[-1].lower() in ("min", "max"):
                value_kind = chain[-1].lower()
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
                    qualifiers=qualifiers,
                    value_kind=value_kind,
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
