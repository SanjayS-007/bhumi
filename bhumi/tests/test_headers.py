from bhumi.read.headers import detect_header_row_count, resolve_headers

ROWS = [
    ["Seam", "BH No", "Thickness (m)", "Thickness (m)", "Ash %", "GCV (kcal/kg)", "Grade"],
    ["Seam", "BH No", "Gross", "Net", "Ash %", "GCV (kcal/kg)", "Grade"],
    ["Seam III Top", "SKM-12", "3.42", "2.91", "34.2", "4180", "G9"],
]


def test_detect_header_row_count():
    assert detect_header_row_count(ROWS) == 2


def test_resolve_headers_two_level_spanning_column():
    assert resolve_headers(ROWS, 2, 2) == ["Thickness (m)", "Gross"]
    assert resolve_headers(ROWS, 2, 3) == ["Thickness (m)", "Net"]


def test_resolve_headers_single_level_column():
    assert resolve_headers(ROWS, 2, 0) == ["Seam"]
    assert resolve_headers(ROWS, 2, 4) == ["Ash %"]


def test_detect_header_row_count_flags_malformed_table():
    """A table where the first row is already mostly numeric should not be
    treated as having a 2-row header."""
    malformed = [["1", "2", "3"], ["Seam III", "SKM-12", "3.42"]]
    assert detect_header_row_count(malformed) == 1
