"""Weakest-link confidence composition (design doc M4.3-lite): a candidate
is only as trustworthy as its weakest component, not an average of them."""
from __future__ import annotations


def unit_confidence(unit_source: str | None) -> float:
    if unit_source is None:
        return 0.3
    if unit_source == "explicit_in_cell":
        return 1.0
    if unit_source.startswith("column_header"):
        return 0.9
    if unit_source == "rulebook_default":
        return 0.6
    return 0.5


def compose_confidence(extraction_confidence: float, unit_source: str | None, entity_resolved: bool) -> float:
    entity_score = 1.0 if entity_resolved else 0.5
    return round(min(extraction_confidence, unit_confidence(unit_source), entity_score), 3)
