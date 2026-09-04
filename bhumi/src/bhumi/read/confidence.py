"""Confidence scorer (design doc M2.9/M4.3-lite). Weakest-link composition:
a fact is only as trustworthy as its weakest component, not an average."""
from __future__ import annotations

TIER_PRIOR = {1: 0.95}


def table_grid_consistency(num_rows: int, num_cols: int, cell_count: int) -> float:
    """Deterministic check: do the cells actually tile num_rows x num_cols
    with no gaps? Requires no model."""
    return 1.0 if cell_count == num_rows * num_cols else 0.5


def element_confidence(page_quality: float, tier: int, structural: float = 1.0) -> float:
    tier_prior = TIER_PRIOR.get(tier, 0.5)
    return round(min(page_quality, tier_prior, structural), 3)
