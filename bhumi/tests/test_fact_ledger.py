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


def test_a_real_extracted_candidate_revised_and_reproduced_as_of(tmp_path):
    """addon 3 §4.1: "against a real revision if one exists in the
    corpus (or a deliberately constructed one if not, clearly marked as
    such)." No two of the real 3-document corpus's own extraction runs
    naturally produce a second version of the same fact — so this
    deliberately constructs one, starting from a REAL Assay-extracted
    candidate (not a hand-built row like `_candidate()` above) and
    revising it with a copy whose value is deliberately changed. Clearly
    marked as constructed, not presented as a found real-world revision.
    """

    from bhumi.acquire.registry import register_local_file
    from bhumi.assay.pipeline import run_assay
    from bhumi.domain.pack_loader import load_default_pack
    from bhumi.read.pipeline import run_read_pipeline
    from bhumi.storage.db.models import DocumentAst
    from scripts.make_sample_pdf import make_sample_pdf

    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="REVISION-TEST-DOC", title="t",
            publisher="CMPDI", doc_kind="sample", classification="public",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())

        real_candidate = session.query(CandidateFactRow).filter_by(doc_id="REVISION-TEST-DOC", state="auto_passed").first()
        if real_candidate is None:
            real_candidate = session.query(CandidateFactRow).filter_by(doc_id="REVISION-TEST-DOC", state="pending_review").first()
        real_candidate.state = "published"
        fact_v1 = publish_fact(session, real_candidate, approver="geologist_1")
        original_value = fact_v1.value
        t_after_v1 = datetime.now(timezone.utc)

        # a deliberately constructed "revision": a second candidate row,
        # identical identity, a genuinely different value — every other
        # field copied from the real extracted one, not a fresh
        # hand-built fixture (ORM objects don't deepcopy cleanly, so
        # fields are copied explicitly instead)
        new_value = original_value + Decimal("0.5")
        revised = CandidateFactRow(
            candidate_id="REVISION-TEST-DOC-revised", doc_id=real_candidate.doc_id,
            entity_raw=real_candidate.entity_raw, entity_id=real_candidate.entity_id,
            metric_raw=real_candidate.metric_raw, metric_key=real_candidate.metric_key,
            value_raw=str(new_value), value=new_value, unit=real_candidate.unit,
            unit_source=real_candidate.unit_source, qualifiers=real_candidate.qualifiers,
            value_kind=real_candidate.value_kind, period=real_candidate.period, status=real_candidate.status,
            source=real_candidate.source, extraction_confidence=real_candidate.extraction_confidence,
            domain_type=real_candidate.domain_type, domain_pack_version=real_candidate.domain_pack_version,
            state="published", confidence=real_candidate.confidence, gate_results=[],
            assay_run_id=real_candidate.assay_run_id,
        )
        session.add(revised)
        session.commit()
        fact_v2 = publish_fact(session, revised, approver="geologist_2")

        assert fact_v2.supersedes == fact_v1.fact_id
        assert fact_v1.system_to is not None

        current = current_facts(session, fact_identity=fact_v1.fact_identity)
        assert current[0].value == original_value + Decimal("0.5")

        as_of_before = as_of(session, t_after_v1, fact_identity=fact_v1.fact_identity)
        assert as_of_before[0].value == original_value  # the real extracted value, reproduced exactly
