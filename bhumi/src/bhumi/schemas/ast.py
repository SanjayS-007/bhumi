"""BHUMI document AST — a deliberately-simplified DoclingDocument-shaped tree.

One output schema regardless of which read tier ran (CLAUDE.md rule).
Tier 1 (PyMuPDF) constructs this directly; a future Tier 2 (Docling) would
normalise its own DoclingDocument into the same shape.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from bhumi.schemas.core import BBox


class TableCell(BaseModel):
    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    column_header: bool = False
    bbox: Optional[BBox] = None
    footnote_markers: list[str] = []


class TableElement(BaseModel):
    element_id: str
    label: Literal["table"] = "table"
    page_no: int
    bbox: BBox
    caption: Optional[str] = None
    num_rows: int
    num_cols: int
    cells: list[TableCell]
    tier: int
    confidence: float


class TextElement(BaseModel):
    element_id: str
    label: Literal["text", "section_header"] = "text"
    page_no: int
    bbox: BBox
    text: str
    tier: int
    confidence: float


class PageInfo(BaseModel):
    page_no: int
    width: float
    height: float
    quality_score: float
    text_coverage: float
    has_text_layer: bool
    is_scanned: bool
    rotation: int
    aspect_anomaly: bool
    raster_path: Optional[str] = None


class RouteDecision(BaseModel):
    page_no: int
    tier: int
    reason: str


class BhumiDocument(BaseModel):
    """Root of the per-document AST, persisted to data/ast/<doc_id>.json."""

    schema_name: Literal["BhumiDocument"] = "BhumiDocument"
    version: str = "1"
    doc_id: str
    artifact_id: str
    pages: list[PageInfo]
    texts: list[TextElement] = []
    tables: list[TableElement] = []
    routing: list[RouteDecision] = []
