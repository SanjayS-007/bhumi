"""Footnote-marker detector (design doc M2.8). Detects trailing markers like
*, †, (a) in a cell so downstream doesn't misread '34.2*' as a bad float.
Linking the marker to its footnote text elsewhere on the page is a stretch
goal not implemented in MVP-1 — only detection + stripping.
"""
from __future__ import annotations

import re

_MARKER_RE = re.compile(r"(\*+|†+|‡+|\([a-zA-Z]\))\s*$")


def extract_footnote_markers(text: str) -> tuple[list[str], str]:
    m = _MARKER_RE.search(text)
    if not m:
        return [], text
    marker = m.group(1)
    clean = text[: m.start()].strip()
    return [marker], clean
