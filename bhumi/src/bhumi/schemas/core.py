"""Canonical schemas — the contract between every phase. See CLAUDE.md rule 6/9."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class BBox(BaseModel):
    """A rectangle on a page. The physical basis of every provenance claim."""

    page_no: int
    l: float
    t: float
    r: float
    b: float
    coord_origin: Literal["TOPLEFT", "BOTTOMLEFT"] = "TOPLEFT"


class SourceRef(BaseModel):
    """Where something came from. Immutable once written."""

    artifact_id: str
    doc_id: str
    version: str = "v1"
    page_no: int
    element_id: str
    bbox: Optional[BBox] = None
    table_ref: Optional[str] = None
    cell_ref: Optional[str] = None


class SourceRegistration(BaseModel):
    artifact_id: str
    doc_id: str
    title: str
    publisher: Literal[
        "CMPDI", "GSI", "MECL", "IBM", "NCDC", "CIL", "STATE_DGM", "CCO", "MOC",
        "PARLIAMENT", "OTHER",
    ]
    doc_kind: Literal[
        "geological_report", "project_report", "annual_report",
        "statistical_return", "closure_plan", "eia_emp", "pq_reply",
        "format_spec", "sample",
    ]
    authority_rank: int = 5
    status: Literal["final", "provisional", "draft"] = "final"
    classification: Literal["public", "internal", "restricted"] = "public"
    published_on: Optional[date] = None
    retrieved_at: datetime
    source_url: Optional[str] = None
    page_count: int
    stage: Optional[Literal["G1", "G2", "G3", "G4"]] = None
    coalfield: Optional[str] = None
    block: Optional[str] = None
    notes: Optional[str] = None


class CandidateFact(BaseModel):
    """A number we think might be a fact. Not yet trusted. Emitted by Phase 3
    (domain typing), gated by Phase 4 (Assay)."""

    candidate_id: str
    entity_raw: str
    entity_id: Optional[str] = None
    metric_raw: str
    metric_key: Optional[str] = None
    value_raw: str
    value: Optional[Decimal] = None
    unit_raw: Optional[str] = None
    unit: Optional[str] = None
    unit_source: Optional[str] = None
    qualifiers: dict[str, str] = {}
    # A real Min/Max range table (docs/REAL_DOC_FINDINGS.md #9) reports two
    # statistics per metric via separate columns, not two data rows — this
    # is what that column distinction becomes on the candidate.
    value_kind: Literal["point", "min", "max"] = "point"
    period: Optional[str] = None
    status: Optional[Literal["final", "provisional", "draft"]] = None
    source: SourceRef
    extraction_confidence: float
    domain_type: Optional[str] = None
    domain_pack_version: Optional[int] = None
