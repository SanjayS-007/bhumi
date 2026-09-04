from bhumi.read.headers import column_x_ranges, detect_header_row_count, resolve_headers

# Convention A: this codebase's own synthetic sample generator repeats
# spanning header text across every spanned column. Still must work.
SYNTHETIC_ROWS = [
    ["Seam", "BH No", "Thickness (m)", "Thickness (m)", "Ash %", "GCV (kcal/kg)", "Grade"],
    ["Seam", "BH No", "Gross", "Net", "Ash %", "GCV (kcal/kg)", "Grade"],
    ["Seam III Top", "SKM-12", "3.42", "2.91", "34.2", "4180", "G9"],
]

# Convention B: verified against the real Marwatola I&II G2 CMPDI report
# (docs/REAL_DOC_FINDINGS.md) — a spanning header's text lives ONCE, in the
# leftmost spanned column; every other spanned column is a true blank with
# no bbox of its own. Reconstructed here at a smaller scale with real-style
# per-cell bboxes (x0, y0, x1, y1).
REAL_STYLE_ROWS = [
    ["Seam Name", "Range Thickness (m)", None, "Ash %", "GCV"],
    [None, "Min", "Max", None, None],
    ["Seam III Top", "3.10", "3.60", "34.2", "4180"],
]
REAL_STYLE_BBOXES = [
    [(0, 0, 50, 10), (50, 0, 150, 10), None, (150, 0, 200, 10), (200, 0, 250, 10)],
    [None, (50, 10, 100, 20), (100, 10, 150, 20), None, None],
    [(0, 20, 50, 30), (50, 20, 100, 30), (100, 20, 150, 30), (150, 20, 200, 30), (200, 20, 250, 30)],
]


def test_detect_header_row_count():
    assert detect_header_row_count(SYNTHETIC_ROWS) == 2
    assert detect_header_row_count(REAL_STYLE_ROWS) == 2


def test_resolve_headers_synthetic_repeated_text_convention():
    assert resolve_headers(SYNTHETIC_ROWS, 2, 2) == ["Thickness (m)", "Gross"]
    assert resolve_headers(SYNTHETIC_ROWS, 2, 3) == ["Thickness (m)", "Net"]
    assert resolve_headers(SYNTHETIC_ROWS, 2, 0) == ["Seam"]


def test_resolve_headers_real_merged_header_needs_bbox_fallback():
    ranges = column_x_ranges(REAL_STYLE_BBOXES, 5)
    # column 2 ("Max") has no text of its own in row 0 — the merge parent's
    # text only exists at column 1's cell, whose bbox happens to span both.
    assert resolve_headers(REAL_STYLE_ROWS, 2, 2, cell_bboxes=REAL_STYLE_BBOXES, col_ranges=ranges) == [
        "Range Thickness (m)", "Max",
    ]
    assert resolve_headers(REAL_STYLE_ROWS, 2, 1, cell_bboxes=REAL_STYLE_BBOXES, col_ranges=ranges) == [
        "Range Thickness (m)", "Min",
    ]


def test_resolve_headers_without_bbox_info_degrades_to_direct_hits_only():
    """No bbox info supplied (e.g. a blank cell with no recorded bbox) ->
    no fallback is attempted; a genuinely unresolvable header returns an
    empty/partial chain rather than guessing."""
    assert resolve_headers(REAL_STYLE_ROWS, 2, 2) == ["Max"]


def test_detect_header_row_count_flags_malformed_table():
    malformed = [["1", "2", "3"], ["Seam III", "SKM-12", "3.42"]]
    assert detect_header_row_count(malformed) == 1
