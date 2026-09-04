"""Header resolution — walk header rows to build the chain for a data cell,
e.g. ["Thickness (m)", "Gross"]. ~40 lines, every unit inference downstream
depends on this (design doc M2.7).

Convention assumed: when a header spans multiple columns, the extractor
repeats the parent header text in every spanned column (rather than leaving
blanks) — see read/tiers/tier1_pymupdf.py and scripts/make_sample_pdf.py.
This sidesteps needing real merged-cell span metadata, which PyMuPDF's
table extraction does not reliably expose.
"""
from __future__ import annotations

import re

_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?%?$")


def _is_numeric(cell: str | None) -> bool:
    if not cell:
        return False
    return bool(_NUMERIC_RE.match(cell.strip()))


def detect_header_row_count(rows: list[list[str | None]], threshold: float = 0.3) -> int:
    """Leading rows are header rows until a row is more than `threshold`
    numeric — a deterministic heuristic, not a model."""
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


def resolve_headers(rows: list[list[str | None]], header_row_count: int, col: int) -> list[str]:
    """Return the header chain for `col`, e.g. ["Thickness (m)", "Gross"].
    Skips blanks; collapses consecutive duplicate text (the repeated-parent
    convention above)."""
    chain: list[str] = []
    for r in range(min(header_row_count, len(rows))):
        row = rows[r]
        val = row[col] if col < len(row) else None
        if val and val.strip():
            v = val.strip()
            if not chain or chain[-1] != v:
                chain.append(v)
    return chain
