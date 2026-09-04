"""Tier router (design doc M2.2). Records the decision and its inputs so the
cost/accuracy story is built from real records, not claims. On this profile
only Tier 1 exists — a scanned page with no text layer has nowhere to go but
the review queue (honest degradation, not a crash)."""
from __future__ import annotations

from dataclasses import dataclass

from bhumi.read.classifier import PageProfile

QUALITY_FLOOR_FOR_TIER1 = 0.55


@dataclass
class RouteResult:
    tier: int | None  # None => no read tier can handle this page
    reason: str


def route_page(profile: PageProfile) -> RouteResult:
    if profile.aspect_anomaly:
        return RouteResult(None, f"aspect ratio anomaly ({profile.width:.0f}x{profile.height:.0f}) — likely fold-out map, declared failure not extracted")
    if profile.has_text_layer and profile.quality_score >= QUALITY_FLOOR_FOR_TIER1:
        return RouteResult(1, f"born-digital, quality {profile.quality_score} >= {QUALITY_FLOOR_FOR_TIER1}")
    return RouteResult(None, f"quality {profile.quality_score} < {QUALITY_FLOOR_FOR_TIER1} and no OCR tier (Tier 2/3) available on profile=sqlite")
