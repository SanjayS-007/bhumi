"""Element-level confidence (design doc M2.9 / M4.3-lite), deliberately
separate from PageQuality (classifier.py).

PageQuality asks "is this page legible?" and drives tier ROUTING.
ElementConfidence asks "did we get THIS cell right?" and drives the ASSAY.
Prose density belongs to neither. A born-digital page read via Tier 1 has
no OCR uncertainty at all — for it, confidence is driven entirely by
deterministic structural checks (does the grid tile cleanly? did the header
chain resolve?), not by how much surrounding text there was.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TIER_PRIOR = {1: 0.95}


@dataclass
class ElementConfidence:
    text_source: Literal["text_layer", "ocr"]
    ocr_token_confidence: float | None
    grid_consistency: float
    header_resolved: bool
    cell_nonblank: bool
    tier: int
    score: float


def table_grid_consistency(num_rows: int, num_cols: int, cell_count: int) -> float:
    """Deterministic check: do the cells actually tile num_rows x num_cols
    with no gaps? Requires no model."""
    return 1.0 if cell_count == num_rows * num_cols else 0.5


def compute_element_confidence(
    tier: int,
    grid_consistency: float,
    header_resolved: bool,
    cell_nonblank: bool,
    text_source: Literal["text_layer", "ocr"] = "text_layer",
    ocr_token_confidence: float | None = None,
) -> ElementConfidence:
    if not cell_nonblank:
        return ElementConfidence(text_source, ocr_token_confidence, grid_consistency, header_resolved, False, tier, 0.0)

    components = [TIER_PRIOR.get(tier, 0.5), grid_consistency, 1.0 if header_resolved else 0.3]
    if text_source == "ocr" and ocr_token_confidence is not None:
        components.append(ocr_token_confidence)
    score = round(min(components), 3)
    return ElementConfidence(text_source, ocr_token_confidence, grid_consistency, header_resolved, True, tier, score)
