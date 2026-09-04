"""Integration test for the reeval recovery loop (design doc M4.4's `task
assay reeval` demo), using an in-memory pack rather than the real mutable
YAML file so this test's outcome doesn't depend on the pack's current
contents."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.assay.gates import run_gates
from bhumi.assay.reeval import reeval_soft_rejected
from bhumi.config.settings import Settings
from bhumi.domain.pack import ColumnRule, DomainPack, EntityPattern, TableTypeDef
from bhumi.schemas.core import BBox, CandidateFact, SourceRef
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import CandidateFactRow

RULES: list[dict] = []
KNOWN_METRICS = {"seam_thickness_gross"}


def _narrow_pack(version: int, widened: bool) -> DomainPack:
    sep = r"[\s.\-]+" if widened else r"[\s-]+"
    return DomainPack(
        pack="test", version=version,
        table_types={"t": TableTypeDef(columns=[ColumnRule(match=["x"], role="entity", entity_type="borehole")])},
        entity_patterns={"borehole": EntityPattern(regex=rf"\b(SKM){sep}(\d+)\b", normalise="{prefix}-{number}")},
    )


def _persist_soft_rejected(session: Session, entity_raw: str) -> str:
    fact = CandidateFact(
        candidate_id="c1", entity_raw=entity_raw, entity_id=None, metric_raw="gross",
        metric_key="seam_thickness_gross", value_raw="3.3", value=Decimal("3.3"), unit="m",
        unit_source="column_header:x", period="p", status="final",
        source=SourceRef(artifact_id="a", doc_id="D", page_no=1, element_id="e",
                         bbox=BBox(page_no=1, l=0, t=0, r=1, b=1)),
        extraction_confidence=0.95, domain_type="t", domain_pack_version=1,
    )
    verdict = run_gates(fact, [], KNOWN_METRICS)  # entity_id=None -> soft_rejected at G2
    session.add(CandidateFactRow(
        candidate_id=fact.candidate_id, doc_id="D", entity_raw=fact.entity_raw, entity_id=fact.entity_id,
        metric_raw=fact.metric_raw, metric_key=fact.metric_key, value_raw=fact.value_raw, value=fact.value,
        unit=fact.unit, unit_source=fact.unit_source, qualifiers={}, period=fact.period, status=fact.status,
        source=fact.source.model_dump(), extraction_confidence=fact.extraction_confidence,
        domain_type=fact.domain_type, domain_pack_version=1,
        state=verdict.state, confidence=verdict.confidence, gate_results=verdict.gate_results,
        failed_gate=verdict.failed_gate, failure_reason=verdict.failure_reason, assay_run_id="r1",
    ))
    session.commit()
    return fact.candidate_id


def test_reeval_recovers_after_entity_pattern_widened(tmp_path, monkeypatch):
    monkeypatch.setattr("bhumi.assay.reeval.load_rules", lambda path: RULES)
    monkeypatch.setattr("bhumi.assay.pipeline.load_known_metric_keys", lambda: KNOWN_METRICS)

    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)

    with Session(engine) as session:
        _persist_soft_rejected(session, "SKM.7")
        row = session.get(CandidateFactRow, "c1")
        assert row.state == "soft_rejected"
        assert row.entity_raw == "SKM.7"  # the fix this test guards: raw text must survive

        result = reeval_soft_rejected(session, "widen separator", _narrow_pack(1, widened=False))
        assert result["recovered"] == 0  # same narrow pack -> still can't resolve "SKM.7"

        result = reeval_soft_rejected(session, "widen separator", _narrow_pack(2, widened=True))
        assert result["recovered"] == 1

        row = session.get(CandidateFactRow, "c1")
        assert row.state != "soft_rejected"
        assert row.entity_id == "SKM-7"
        assert row.domain_pack_version == 2
        assert row.reeval_count == 2


def test_reeval_never_touches_published_or_pending_rows(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    with Session(engine) as session:
        cid = _persist_soft_rejected(session, "SKM.9")
        row = session.get(CandidateFactRow, cid)
        row.state = "published"  # simulate a human having already approved it
        session.commit()

        reeval_soft_rejected(session, "unrelated pack bump", _narrow_pack(2, widened=True))

        row = session.execute(select(CandidateFactRow).where(CandidateFactRow.candidate_id == cid)).scalar_one()
        assert row.state == "published"
        assert row.reeval_count == 0
