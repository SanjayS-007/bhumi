"""Unit resolution (design doc M3.4, steps that apply to this corpus).
Never infer a unit — six-step order in the full design collapses to three
here because MVP-2's synthetic corpus never embeds a unit in the cell text
itself: header text -> rulebook default (expect_unit) -> reject."""
from __future__ import annotations

import re

from bhumi.domain.pack import ColumnRule

_HEADER_UNIT_RE = re.compile(r"\(([^)]+)\)|(%)")


def resolve_unit(col: ColumnRule, header_chain: list[str]) -> tuple[str | None, str | None]:
    if col.unit_from_header:
        for h in header_chain:
            m = _HEADER_UNIT_RE.search(h)
            if m:
                unit = m.group(1) or m.group(2)
                return unit, f"column_header:{h}"
    if col.expect_unit:
        return col.expect_unit, "rulebook_default"
    return None, None
