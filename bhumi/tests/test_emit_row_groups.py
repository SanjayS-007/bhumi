"""Row-group / continuation-row handling (docs/REAL_DOC_FINDINGS.md #9,
fixed 2026-09-06): a real seam's values row is sometimes followed by a
blank-identity borehole-reference row. It must not spawn spurious
candidates, and its borehole mentions must be captured on the owning row.
"""
from bhumi.domain.emit import emit_candidates
from bhumi.domain.pack import ColumnRule, DomainPack, EntityPattern, TableTypeDef


def _pack() -> DomainPack:
    return DomainPack(
        pack="test", version=1,
        table_types={
            "range": TableTypeDef(columns=[
                ColumnRule(match=["seam name"], role="entity", entity_type="seam"),
                ColumnRule(match=["gross"], role="metric", metric_key="seam_thickness_gross",
                           expect_unit="m", stat_from_header=True),
            ]),
        },
        entity_patterns={
            "seam": EntityPattern(regex=r"\b([IVXL]+)\s*(Top|Bottom)?\b", normalise="{roman} {position}"),
            "borehole": EntityPattern(regex=r"\b(MSM)-(\d+)\b", normalise="{prefix}-{number}"),
        },
    )


def _table(rows: list[list[str]]) -> dict:
    n_cols = len(rows[0])
    cells = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cells.append({"row": r, "col": c, "text": text, "bbox": None, "column_header": r == 0})
    return {
        "element_id": "t0", "page_no": 1, "num_rows": len(rows), "num_cols": n_cols,
        "cells": cells, "confidence": 0.95,
    }


def test_continuation_row_produces_no_candidates_but_is_captured_as_provenance():
    table = _table([
        ["Seam Name", "Gross"],
        ["IV", "1.8"],
        ["", "MSM-17"],  # continuation row: blank identity, borehole reference
    ])
    candidates = emit_candidates("D", "A", table, "range", _pack().table_types["range"], _pack())
    assert len(candidates) == 1
    c = candidates[0]
    assert c.entity_id == "IV"
    assert c.value_kind in ("point", "min", "max")  # header has no Min/Max sub-row here, "point" is correct
    assert c.qualifiers.get("source_boreholes") == "MSM-17"


def test_single_row_per_record_table_unaffected():
    """No continuation row present -> behaves exactly as before this fix."""
    table = _table([
        ["Seam Name", "Gross"],
        ["IV", "1.8"],
        ["III", "3.4"],
    ])
    candidates = emit_candidates("D", "A", table, "range", _pack().table_types["range"], _pack())
    assert len(candidates) == 2
    assert {c.entity_id for c in candidates} == {"IV", "III"}
    assert all("source_boreholes" not in c.qualifiers for c in candidates)
