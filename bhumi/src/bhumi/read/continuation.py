"""Multi-page table continuation (design doc's TableContinuation). Verified
real on the actual Marwatola GR: pages 15/16 (1-indexed) share an identical
header row and are one logical table split by a page break — confirmed by
direct header comparison, not assumed. Detection signal used: `repeated_header`
only (the simplest, and the one actually observed); `caption_continued` and
`page_boundary_row_match` are not implemented — no real example of either
was found, so building them now would be speculative. Merge happens here,
before domain typing runs, per the design doc's explicit ordering.
"""
from __future__ import annotations

from bhumi.schemas.ast import TableElement


def _header_signature(t: TableElement) -> tuple:
    return tuple(sorted((c.row, c.col, c.text) for c in t.cells if c.column_header))


def _last_page(t: TableElement) -> int:
    pages = [c.bbox.page_no for c in t.cells if c.bbox]
    return max(pages) if pages else t.page_no


def merge_continued_tables(tables: list[TableElement]) -> list[TableElement]:
    if not tables:
        return []
    merged: list[TableElement] = [tables[0]]
    for t in tables[1:]:
        prev = merged[-1]
        if t.page_no == _last_page(prev) + 1 and _header_signature(t) == _header_signature(prev):
            header_row_count = max((c.row for c in t.cells if c.column_header), default=-1) + 1
            row_offset = prev.num_rows
            for c in t.cells:
                if c.row < header_row_count:
                    continue  # drop the repeated header, keep prev's own
                prev.cells.append(c.model_copy(update={"row": c.row - header_row_count + row_offset}))
            prev.num_rows = row_offset + (t.num_rows - header_row_count)
            prev.confidence = min(prev.confidence, t.confidence)
            continue
        merged.append(t)
    return merged
