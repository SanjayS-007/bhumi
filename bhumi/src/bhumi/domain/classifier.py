"""Table-type classifier (design doc M3.1): caption match -> header-signature
match -> unclassified. No LLM fallback stage in MVP-2 — the corpus is small
enough that the two deterministic stages are expected to cover it; add a
stage 3 if/when a real corpus proves them insufficient."""
from __future__ import annotations

import re
from dataclasses import dataclass

from bhumi.domain.pack import DomainPack, TableTypeDef


@dataclass
class ClassificationResult:
    table_type: str | None
    confidence: float
    stage: str


def find_caption(ast: dict, table: dict) -> str | None:
    """Nearest text block directly above the table on the same page."""
    candidates = [
        t for t in ast["texts"]
        if t["page_no"] == table["page_no"] and t["bbox"]["b"] <= table["bbox"]["t"]
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: t["bbox"]["b"])["text"]


def _flatten_headers(table: dict) -> set[str]:
    words: set[str] = set()
    for cell in table["cells"]:
        if cell["column_header"] and cell["text"]:
            words.update(re.findall(r"[a-z%]+", cell["text"].lower()))
    return words


def classify_table(pack: DomainPack, caption: str | None, table: dict) -> ClassificationResult:
    header_words = _flatten_headers(table)

    if caption:
        for name, td in pack.table_types.items():
            for pat in td.caption_patterns:
                if re.search(pat, caption, re.IGNORECASE):
                    return ClassificationResult(name, 0.95, "caption")

    best: tuple[str, int, TableTypeDef] | None = None
    for name, td in pack.table_types.items():
        sig = {s.lower() for s in td.header_signature}
        overlap = len(sig & header_words)
        if overlap >= td.min_signature_overlap and (best is None or overlap > best[1]):
            best = (name, overlap, td)
    if best:
        return ClassificationResult(best[0], 0.85, "header_signature")

    return ClassificationResult(None, 0.0, "unclassified")
