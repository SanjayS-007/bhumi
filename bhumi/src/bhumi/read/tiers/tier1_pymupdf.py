"""Tier 1 — PyMuPDF. Born-digital text + table extraction. Zero VRAM, always
available. This alone is what makes MVP-1 work on this machine (no Docling,
no GPU).

Confidence is computed here, self-contained, using the ElementConfidence
model (read/confidence.py) — NOT the page's prose-density-free quality
score, which only drives tier routing. A clean born-digital table scores
high regardless of how much surrounding text the page has.
"""
from __future__ import annotations

from bhumi.read.confidence import TIER_PRIOR, compute_element_confidence, table_grid_consistency
from bhumi.read.footnotes import extract_footnote_markers
from bhumi.read.headers import column_x_ranges, detect_header_row_count, resolve_headers
from bhumi.schemas.ast import BBox, TableCell, TableElement, TextElement

TIER = 1


def extract_text_elements(page, page_no: int) -> list[TextElement]:
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
                confidence=TIER_PRIOR[TIER],
            )
        )
    return elements


def extract_tables(page, page_no: int) -> list[TableElement]:
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
        bbox_grid: list[list[tuple | None]] = [
            [row_cell_bboxes[r][c] if row_cell_bboxes[r] and c < len(row_cell_bboxes[r]) else None
             for c in range(n_cols)]
            for r in range(n_rows)
        ]
        col_ranges = column_x_ranges(bbox_grid, n_cols)
        grid_conf = table_grid_consistency(n_rows, n_cols, sum(len(r) for r in rows_text))

        cells: list[TableCell] = []
        data_confidences: list[float] = []
        for r, row in enumerate(rows_text):
            for c in range(n_cols):
                raw = row[c] if c < len(row) else None
                # Real PDFs embed literal newlines inside cell text when a
                # value wraps near a source line break (e.g. "CSM \nI&II-01")
                # — collapse before anything downstream sees it. Verified
                # against a real CMPDI GR; see docs/REAL_DOC_FINDINGS.md #4.
                raw_clean = " ".join(raw.split()) if raw else raw
                markers, clean = extract_footnote_markers(raw_clean or "")
                bbox = None
                if bbox_grid[r][c]:
                    bx0, by0, bx1, by1 = bbox_grid[r][c]
                    bbox = BBox(page_no=page_no, l=bx0, t=by0, r=bx1, b=by1)

                is_header = r < header_row_count
                if is_header:
                    ec_score, header_resolved = TIER_PRIOR[TIER], True
                else:
                    chain = resolve_headers(rows_text, header_row_count, c, cell_bboxes=bbox_grid, col_ranges=col_ranges)
                    header_resolved = len(chain) > 0
                    ec = compute_element_confidence(
                        tier=TIER, grid_consistency=grid_conf, header_resolved=header_resolved,
                        cell_nonblank=bool(clean.strip()),
                    )
                    ec_score = ec.score
                    if clean.strip():
                        data_confidences.append(ec_score)

                cells.append(
                    TableCell(
                        text=clean,
                        row=r,
                        col=c,
                        column_header=is_header,
                        bbox=bbox,
                        footnote_markers=markers,
                        confidence=ec_score,
                        header_resolved=header_resolved,
                    )
                )

        x0, y0, x1, y1 = table.bbox
        table_confidence = min(data_confidences) if data_confidences else TIER_PRIOR[TIER]
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
                confidence=round(table_confidence, 3),
            )
        )
    return elements
