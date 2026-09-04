"""Synthesize a small multi-page PDF with a realistic two-level-header
seam-thickness table, using only PyMuPDF drawing primitives. Zero external
downloads — this is what makes `task ingest -- --sample` work fully
offline, in CI, and for a teammate with no corpus.
"""
from __future__ import annotations

from pathlib import Path

import fitz

TABLE_ROWS = [
    # header row 0 — spanning "Thickness (m)" repeated across its two columns
    ["Seam", "BH No", "Thickness (m)", "Thickness (m)", "Ash %", "GCV (kcal/kg)", "Grade"],
    # header row 1 — second level under Thickness (m); repeated elsewhere
    ["Seam", "BH No", "Gross", "Net", "Ash %", "GCV (kcal/kg)", "Grade"],
    # data rows
    ["Seam III Top", "SKM-12", "3.42", "2.91", "34.2*", "4180", "G9"],
    ["Seam III Top", "SKM-14", "3.38", "2.85", "33.9", "4150", "G9"],
    # deliberately-bad row for the Assay demo: net (3.60) > gross (3.10) is
    # physically impossible — a synthetic stand-in for an OCR digit error,
    # so MVP-2's net_le_gross rule has something real to catch and reject.
    ["Seam III Top", "SKM-16", "3.10", "3.60", "35.1", "4120", "G9"],
    # deliberately-unmatched borehole ID spelling variant, for the Assay
    # reeval demo: the shipped entity pattern doesn't accept "." as a
    # prefix/number separator, so this row's candidates soft-reject at
    # G2 (missing entity_id) until a domain-pack update widens the regex.
    ["Seam III Top", "SKM.18", "3.30", "2.80", "34.0", "4160", "G9"],
]


def make_sample_pdf(out_path: Path) -> Path:
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 72), "Final Geological Report (SAMPLE)", fontsize=16)
    page1.insert_text((72, 100), "Marwatola Sector I & II Block, Sohagpur Coalfield", fontsize=11)
    page1.insert_text((72, 118), "District Shahdol, Madhya Pradesh — G2 stage — CMPDI (synthetic sample document)", fontsize=10)
    page1.insert_text((72, 160), "Chapter 6 - Seam Correlation and Thickness", fontsize=12)

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Table 6.2 - Seam-wise thickness by borehole, Marwatola Sector I & II", fontsize=10)

    x0, y0 = 72, 100
    col_widths = [70, 55, 45, 45, 45, 70, 45]
    row_height = 20
    n_rows = len(TABLE_ROWS)
    n_cols = len(col_widths)

    col_x = [x0]
    for w in col_widths:
        col_x.append(col_x[-1] + w)

    for r in range(n_rows):
        ry0 = y0 + r * row_height
        for c in range(n_cols):
            rx0 = col_x[c]
            rect = fitz.Rect(rx0, ry0, rx0 + col_widths[c], ry0 + row_height)
            page2.draw_rect(rect)
            text = TABLE_ROWS[r][c]
            page2.insert_text((rx0 + 3, ry0 + row_height - 6), text, fontsize=7.5)

    footnote_y = y0 + n_rows * row_height + 20
    page2.insert_text((x0, footnote_y), "* includes inferred category (synthetic footnote for demo purposes)", fontsize=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    doc.close()
    return out_path


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample.pdf")
    make_sample_pdf(target)
    print(f"wrote {target}")
