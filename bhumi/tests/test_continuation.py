"""Multi-page table continuation, verified against a real repeated-header
case found in the Marwatola GR (pages 15/16) — see read/continuation.py."""
from bhumi.read.continuation import merge_continued_tables
from bhumi.schemas.ast import BBox, TableCell, TableElement


def _cell(row, col, text, page_no, is_header=False):
    return TableCell(text=text, row=row, col=col, column_header=is_header,
                      bbox=BBox(page_no=page_no, l=0, t=0, r=1, b=1))


def _table(element_id, page_no, header_cols, data_rows):
    cells = [_cell(0, c, h, page_no, is_header=True) for c, h in enumerate(header_cols)]
    for r, row in enumerate(data_rows, start=1):
        cells += [_cell(r, c, v, page_no) for c, v in enumerate(row)]
    return TableElement(
        element_id=element_id, page_no=page_no,
        bbox=BBox(page_no=page_no, l=0, t=0, r=1, b=1),
        num_rows=1 + len(data_rows), num_cols=len(header_cols), cells=cells,
        tier=1, confidence=0.95,
    )


def test_identical_header_on_next_page_merges():
    t1 = _table("p15-table-0", 15, ["Seams", "Depth"], [["IV", "10"]])
    t2 = _table("p16-table-0", 16, ["Seams", "Depth"], [["III", "20"]])
    merged = merge_continued_tables([t1, t2])
    assert len(merged) == 1
    assert merged[0].num_rows == 3  # 1 header + 2 data rows total
    data_texts = sorted(c.text for c in merged[0].cells if not c.column_header)
    assert data_texts == ["10", "20", "III", "IV"]
    # the continuation's own data row must carry its OWN page_no on its bbox
    row2_cells = [c for c in merged[0].cells if c.text == "III"]
    assert row2_cells[0].bbox.page_no == 16


def test_different_header_does_not_merge():
    t1 = _table("p14-table-0", 14, ["Fault No", "Trend"], [["1", "E-W"]])
    t2 = _table("p15-table-0", 15, ["Seams", "Depth"], [["IV", "10"]])
    merged = merge_continued_tables([t1, t2])
    assert len(merged) == 2


def test_non_adjacent_page_does_not_merge():
    t1 = _table("p15-table-0", 15, ["Seams", "Depth"], [["IV", "10"]])
    t2 = _table("p20-table-0", 20, ["Seams", "Depth"], [["III", "20"]])
    merged = merge_continued_tables([t1, t2])
    assert len(merged) == 2
