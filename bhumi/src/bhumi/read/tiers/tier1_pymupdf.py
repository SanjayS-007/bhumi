"""Tier 1 — PyMuPDF. Born-digital text + table extraction. Zero VRAM, always
available. This alone is what makes MVP-1 work on this machine (no Docling,
no GPU)."""
from __future__ import annotations

from bhumi.read.footnotes import extract_footnote_markers
from bhumi.read.headers import detect_header_row_count
from bhumi.schemas.ast import BBox, TableCell, TableElement, TextElement

TIER = 1


def extract_text_elements(page, page_no: int, confidence: float) -> list[TextElement]:
    elements = []
    for i, b in enumerate(page.get_text("blocks")):
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        text = text.strip()
        if not text:
            continue
        elements.append(
            TextElement(
                element_id=f"p{page_no}-text-{i}",
                page_no=page_no,
                bbox=BBox(page_no=page_no, l=x0, t=y0, r=x1, b=y1),
                text=text,
                tier=TIER,
                confidence=confidence,
            )
        )
    return elements


def extract_tables(page, page_no: int, confidence: float) -> list[TableElement]:
    elements: list[TableElement] = []
    finder = page.find_tables()
    for ti, table in enumerate(finder.tables):
        rows_text = table.extract()
        if not rows_text:
            continue
        header_row_count = detect_header_row_count(rows_text)
        n_rows = len(rows_text)
        n_cols = max(len(r) for r in rows_text)

        row_cell_bboxes = [getattr(r, "cells", None) for r in table.rows]

        cells: list[TableCell] = []
        for r, row in enumerate(rows_text):
            for c in range(n_cols):
                raw = row[c] if c < len(row) else None
                markers, clean = extract_footnote_markers(raw or "")
                bbox = None
                if row_cell_bboxes[r] and c < len(row_cell_bboxes[r]) and row_cell_bboxes[r][c]:
                    bx0, by0, bx1, by1 = row_cell_bboxes[r][c]
                    bbox = BBox(page_no=page_no, l=bx0, t=by0, r=bx1, b=by1)
                cells.append(
                    TableCell(
                        text=clean,
                        row=r,
                        col=c,
                        column_header=r < header_row_count,
                        bbox=bbox,
                        footnote_markers=markers,
                    )
                )

        x0, y0, x1, y1 = table.bbox
        elements.append(
            TableElement(
                element_id=f"p{page_no}-table-{ti}",
                page_no=page_no,
                bbox=BBox(page_no=page_no, l=x0, t=y0, r=x1, b=y1),
                caption=None,
                num_rows=n_rows,
                num_cols=n_cols,
                cells=cells,
                tier=TIER,
                confidence=confidence,
            )
        )
    return elements
