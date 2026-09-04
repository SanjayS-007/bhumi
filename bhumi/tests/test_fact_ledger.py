"""The bitemporal reproducibility claim, verified: publish a fact, revise
it, then query as-of a timestamp before the revision and get the original
value back exactly (design doc Phase 5.1)."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from bhumi.config.settings import Settings
from bhumi.knowledge.ledger import as_of, current_facts, fact_identity, history, publish_fact
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import CandidateFactRow


def _candidate(session: Session, candidate_id: str, value: str) -> CandidateFactRow:
    row = CandidateFactRow(
        candidate_id=candidate_id, doc_id="D", entity_raw="IV", entity_id="IV",
        metric_raw="gross", metric_key="seam_thickness_gross", value_raw=value, value=Decimal(value),
        unit="m", unit_source="column_header:x", qualifiers={}, value_kind="min", period="p", status="final",
        source={"artifact_id": "a", "doc_id": "D", "page_no": 1, "element_id": "e"},
        extraction_confidence=0.95, domain_type="t", domain_pack_version=1,
        state="published", confidence=0.9, gate_results=[], assay_run_id="r1",
    )
    session.add(row)
    session.commit()
    return row


def test_publish_then_revise_then_as_of_returns_original_value(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    with Session(engine) as session:
        c1 = _candidate(session, "c1", "1.80")
        fact_v1 = publish_fact(session, c1, approver="geologist_1")
        t_after_v1 = datetime.now(timezone.utc)  # strictly between v1's publish and v2's, below

        c2 = _candidate(session, "c2", "1.90")  # a "revision" — same identity, different value
        c2.entity_id, c2.metric_key, c2.qualifiers, c2.value_kind, c2.period = (
            c1.entity_id, c1.metric_key, c1.qualifiers, c1.value_kind, c1.period,
        )
        fact_v2 = publish_fact(session, c2, approver="geologist_2")

        assert fact_v2.supersedes == fact_v1.fact_id
        assert fact_v1.system_to is not None  # closed, never deleted

        current = current_facts(session, fact_identity=fact_v1.fact_identity)
        assert len(current) == 1
        assert current[0].value == Decimal("1.90")

        as_of_before = as_of(session, t_after_v1, fact_identity=fact_v1.fact_identity)
        assert len(as_of_before) == 1
        assert as_of_before[0].value == Decimal("1.80")  # exactly the original, reproduced

        hist = history(session, fact_v1.fact_identity)
        assert [h.value for h in hist] == [Decimal("1.80"), Decimal("1.90")]


def test_fact_identity_stable_across_qualifier_key_ordering():
    a = fact_identity("IV", "seam_thickness_gross", {"a": "1", "b": "2"}, "p", "min")
    b = fact_identity("IV", "seam_thickness_gross", {"b": "2", "a": "1"}, "p", "min")
    assert a == b


def test_republishing_identical_value_is_a_noop(tmp_path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    with Session(engine) as session:
        c1 = _candidate(session, "c1", "1.80")
        fact_v1 = publish_fact(session, c1, approver="geologist_1")
        c2 = _candidate(session, "c2", "1.80")
        c2.entity_id, c2.metric_key = c1.entity_id, c1.metric_key
        fact_v2 = publish_fact(session, c2, approver="geologist_2")
        assert fact_v1.fact_id == fact_v2.fact_id  # same row, no spurious revision
