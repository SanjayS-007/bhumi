"""Deterministic entity recognition via regex patterns from the domain
pack — no model, no training data (design doc M3.3, Tier A only; Splink/LLM
adjudication tiers are out of scope for MVP-2's small single-document
corpus — see CLAUDE.md rule 8 on not adding machinery for problems this
project doesn't have yet)."""
from __future__ import annotations

import re

from bhumi.domain.pack import EntityPattern

_ROMAN = {"I": "I", "II": "II", "III": "III", "IV": "IV", "V": "V"}


def resolve_entity(entity_type: str, raw: str, pattern: EntityPattern) -> str | None:
    m = re.search(pattern.regex, raw, re.IGNORECASE)
    if not m:
        return None
    groups = {f"g{i}": (g or "") for i, g in enumerate(m.groups())}
    if entity_type == "borehole":
        # Real series verified against the Marwatola I&II G2 GR (docs/
        # REAL_DOC_FINDINGS.md #4): "CSM I&II-01" and "MSM-19", not the
        # design doc's illustrative SKM-12/SGT-07 (which don't occur in
        # any real document checked so far).
        prefix_raw, number = m.group(1).upper(), m.group(2)
        if "MSM" in prefix_raw:
            prefix = "MSM"
        elif "CSM" in prefix_raw:
            prefix = "CSM I&II"
        else:
            prefix = prefix_raw  # SKM/SGT — synthetic sample only, keep as matched
        return pattern.normalise.format(prefix=prefix, number=number)
    if entity_type == "seam":
        roman = m.group(1).upper()
        position = (m.group(2) or "").strip()
        return pattern.normalise.format(roman=roman, position=position).strip()
    return pattern.normalise.format(**groups)
