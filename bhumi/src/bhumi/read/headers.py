"""Header resolution — walk header rows to build the chain for a data cell,
e.g. ["Range of Seam Thickness (m)", "Max"]. Every unit inference downstream
depends on this (design doc M2.7).

Verified against a real CMPDI Geological Report (Marwatola I&II, G2 stage,
NMET) on 2026-09-04: real spanning headers put their text ONCE, in the
leftmost cell of the span, and leave every other spanned cell as a true
`None` — not a repeated string. (An earlier version of this module assumed
repeated text; that assumption held for this codebase's own synthetic
sample generator and nothing else. See docs/REAL_DOC_FINDINGS.md.)

The fix: use real per-cell bounding boxes (PyMuPDF's `table.rows[r].cells`
gives one per grid cell, `None` where a column is spanned away) to find,
by geometry, which header cell actually covers a given data column — instead
of guessing from adjacent text. This handles both conventions: a cell with
its own non-blank text at (row, col) is used directly; a blank/None cell
falls back to whichever cell in that row horizontally contains that
column's x-center.
"""
from __future__ import annotations

import re

_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?%?$")
BBox = tuple[float, float, float, float] | None


def _is_numeric(cell: str | None) -> bool:
    if not cell:
        return False
    return bool(_NUMERIC_RE.match(cell.strip()))


def _clean(text: str) -> str:
    """Real header cells embed literal newlines, e.g. 'Seam\\nName'."""
    return " ".join(text.split())


def detect_header_row_count(rows: list[list[str | None]], threshold: float = 0.3) -> int:
    """Leading rows are header rows until a row is more than `threshold`
    numeric — a deterministic heuristic, not a model. A fully-blank row
    (a spacer, common in real GRs between the header block and data) still
    counts as part of the header block."""
    count = 0
    for row in rows:
        non_empty = [c for c in row if c and c.strip()]
        if not non_empty:
            count += 1
            continue
        numeric_frac = sum(_is_numeric(c) for c in non_empty) / len(non_empty)
        if numeric_frac >= threshold:
            break
        count += 1
    return max(count, 1)


def column_x_ranges(cell_bboxes: list[list[BBox]], n_cols: int) -> list[BBox]:
    """The narrowest bbox observed for each column, across every row, is
    the best estimate of that column's true (unmerged) x-range."""
    ranges: list[BBox] = [None] * n_cols
    for row in cell_bboxes:
        for c in range(min(n_cols, len(row))):
            bbox = row[c]
            if bbox is None:
                continue
            width = bbox[2] - bbox[0]
            cur = ranges[c]
            if cur is None or width < (cur[2] - cur[0]):
                ranges[c] = bbox
    return ranges


def resolve_headers(
    rows: list[list[str | None]],
    header_row_count: int,
    col: int,
    cell_bboxes: list[list[BBox]] | None = None,
    col_ranges: list[BBox] | None = None,
) -> list[str]:
    """Return the header chain for `col`, e.g.
    ["Range of Seam Thickness (m)", "Max"]. Skips blanks; collapses
    consecutive duplicate text. Falls back to bbox-containment for real
    merged-header layouts when `cell_bboxes`/`col_ranges` are supplied
    (they're optional so this still works for header rows with no bbox
    info, e.g. the pre-bbox synthetic-only tests)."""
    chain: list[str] = []
    target_center = None
    if col_ranges and col < len(col_ranges) and col_ranges[col]:
        b = col_ranges[col]
        target_center = (b[0] + b[2]) / 2

    for r in range(min(header_row_count, len(rows))):
        row = rows[r]
        val = row[col] if col < len(row) else None
        if val and val.strip():
            v = _clean(val)
        elif target_center is not None and cell_bboxes and r < len(cell_bboxes):
            v = None
            for c2, bbox in enumerate(cell_bboxes[r]):
                if bbox and bbox[0] <= target_center <= bbox[2]:
                    t2 = row[c2] if c2 < len(row) else None
                    if t2 and t2.strip():
                        v = _clean(t2)
                    break
        else:
            v = None
        if v and (not chain or chain[-1] != v):
            chain.append(v)
    return chain
