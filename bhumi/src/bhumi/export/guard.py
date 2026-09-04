"""Enforces the classification decision (docs/CLASSIFICATION_DECISION.md)
in code, not just discipline. Every path that renders content OUTSIDE the
running app — video capture, screenshot export, the evidence-pack exporter,
any future public API — must call `assert_exportable` first.

"Publicly downloadable" and "classification: public" are not the same
judgment (docs/CLASSIFICATION_DECISION.md §2) — this guard only ever checks
the latter, which is the conservative side of that distinction.
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from bhumi.schemas.core import SourceRef
from bhumi.storage.db.models import SourceRegistry

ExportPurpose = Literal["demo", "video", "public_artifact"]


class ExportBlocked(Exception):
    pass


def get_classification(session: Session, artifact_id: str) -> str:
    row = session.get(SourceRegistry, artifact_id)
    if row is None:
        raise ExportBlocked(f"artifact_id {artifact_id} is not registered — cannot verify classification")
    return row.classification


def assert_exportable(session: Session, source_ref: SourceRef, purpose: ExportPurpose) -> None:
    classification = get_classification(session, source_ref.artifact_id)
    if classification != "public":
        raise ExportBlocked(
            f"{source_ref.doc_id} is classified '{classification}'. "
            f"Cannot be used for purpose='{purpose}'. Use a public-classified document instead."
        )
