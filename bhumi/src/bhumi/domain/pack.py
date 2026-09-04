"""Pydantic shape for a domain pack YAML file (design doc M3.2)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ColumnRule(BaseModel):
    match: list[str]
    role: Literal["entity", "metric", "qualifier"]
    entity_type: Optional[str] = None
    qualifier_key: Optional[str] = None
    metric_key: Optional[str] = None
    expect_unit: Optional[str] = None
    unit_from_header: bool = False
    value_type: Literal["decimal", "categorical"] = "decimal"
    # Real GRs report Min/Max ranges per seam rather than one value per row
    # (docs/REAL_DOC_FINDINGS.md #9) — the statistic isn't a separate data
    # column, it's the last segment of the header chain itself.
    stat_from_header: bool = False


class TableTypeDef(BaseModel):
    caption_patterns: list[str] = []
    header_signature: list[str] = []
    min_signature_overlap: int = 2
    columns: list[ColumnRule] = []


class EntityPattern(BaseModel):
    regex: str
    normalise: str


class DomainPack(BaseModel):
    pack: str
    version: int
    table_types: dict[str, TableTypeDef]
    entity_patterns: dict[str, EntityPattern] = {}
