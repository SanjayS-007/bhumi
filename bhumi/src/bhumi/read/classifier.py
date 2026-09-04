"""Page classifier (design doc M2.1). Pure PyMuPDF, no ML — born-digital vs
scanned, quality score, rotation, aspect-ratio anomaly (fold-out map)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PageProfile:
    page_no: int
    width: float
    height: float
    quality_score: float
    text_coverage: float
    has_text_layer: bool
    is_scanned: bool
    rotation: int
    aspect_anomaly: bool


def classify_page(page, page_no: int) -> PageProfile:
    rect = page.rect
    text = page.get_text().strip()
    has_text_layer = len(text) > 20
    image_count = len(page.get_images())
    text_coverage = min(1.0, len(text) / 2000) if has_text_layer else 0.0

    aspect = rect.width / rect.height if rect.height else 1.0
    aspect_anomaly = aspect > 2.0 or aspect < 0.35

    is_scanned = not has_text_layer and image_count > 0
    if has_text_layer:
        quality_score = 0.6 + 0.4 * text_coverage
    elif is_scanned:
        quality_score = 0.2  # no OCR tier available on this profile — see router.py
    else:
        quality_score = 0.5  # blank/unclear page

    return PageProfile(
        page_no=page_no,
        width=rect.width,
        height=rect.height,
        quality_score=round(quality_score, 3),
        text_coverage=round(text_coverage, 3),
        has_text_layer=has_text_layer,
        is_scanned=is_scanned,
        rotation=page.rotation,
        aspect_anomaly=aspect_anomaly,
    )
