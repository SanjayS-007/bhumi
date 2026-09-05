"""BEDROCK hardening (addon 3 §4.2): three personas (the subsidiary
officer's entity_scope is the genuinely new dimension), audit logging,
package persistence + merge + replay, and the adversarial cache-
correctness case replay() exists specifically to prevent. Against real
ingested/assayed/published data, via the real MCP subprocess protocol.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.assay.pipeline import run_assay
from bhumi.broker.mcp_client import (
    call_tool,
    check_coverage,
    compute_metric,
    get_conformance_report,
    list_geological_tables,
    list_review_queue,
    merge_packages,
    replay,
    seal_evidence_package,
    subsidiary_env,
)
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.ledger import publish_fact
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import AuditLog, CandidateFactRow, DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _setup(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="HARDEN-TEST-DOC", title="t",
            publisher="CMPDI", doc_kind="sample", classification="restricted",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
        published = session.query(CandidateFactRow).filter_by(doc_id="HARDEN-TEST-DOC", state="auto_passed").first()
        if published is None:
            published = session.query(CandidateFactRow).filter_by(doc_id="HARDEN-TEST-DOC", state="pending_review").first()
        published.state = "published"
        fact = publish_fact(session, published, approver="test")
        metric_key = fact.metric_key
    env_overrides = {"BHUMI_DATA_DIR": str(tmp_path), "BHUMI_SQLITE_PATH": str(tmp_path / "bhumi.db")}
    return engine, env_overrides, metric_key


def test_cmpdi_geologist_persona_has_full_internal_access(tmp_path):
    engine, env_overrides, metric_key = _setup(tmp_path)
    coverage = check_coverage(metric_key, "cmpdi_geologist", env_overrides=env_overrides)
    assert coverage["covered"]


def test_subsidiary_officer_sees_own_document_but_not_a_different_one(tmp_path):
    engine, env_overrides, metric_key = _setup(tmp_path)
    scoped_env = {**env_overrides, **subsidiary_env(["HARDEN-TEST-DOC"])}
    figures = compute_metric(metric_key, "subsidiary_officer", env_overrides=scoped_env)
    assert figures  # this subsidiary's own document is visible

    other_scoped_env = {**env_overrides, **subsidiary_env(["SOME-OTHER-DOC-NOT-THEIRS"])}
    figures_other = compute_metric(metric_key, "subsidiary_officer", env_overrides=other_scoped_env)
    assert figures_other == []  # a different subsidiary's document is not


def test_every_authorize_decision_is_audited(tmp_path):
    engine, env_overrides, metric_key = _setup(tmp_path)
    check_coverage(metric_key, "public", env_overrides=env_overrides)
    check_coverage(metric_key, "internal", env_overrides=env_overrides)
    try:
        call_tool("no_such_tool_at_all", {}, "public", env_overrides)
    except Exception:
        pass

    with Session(engine) as session:
        rows = session.query(AuditLog).all()
    subjects = {r.subject for r in rows}
    assert "public_caller" in subjects
    assert "internal_reviewer" in subjects
    assert any(not r.allowed for r in rows)  # the bogus tool call was denied and logged
    assert any(r.allowed for r in rows)


def test_list_review_queue_and_geological_tables_and_conformance_report_are_real(tmp_path):
    engine, env_overrides, metric_key = _setup(tmp_path)
    queue = list_review_queue("internal", doc_id="HARDEN-TEST-DOC", env_overrides=env_overrides)
    assert isinstance(queue, list)  # real query, whatever it finds

    tables = list_geological_tables("HARDEN-TEST-DOC", "internal", env_overrides=env_overrides)
    assert tables and "element_id" in tables[0]

    report = get_conformance_report("HARDEN-TEST-DOC", "internal", env_overrides=env_overrides)
    assert report["found"]
    assert "state_counts" in report

    # a public caller can't see a restricted document's tables at all
    tables_public = list_geological_tables("HARDEN-TEST-DOC", "public", env_overrides=env_overrides)
    assert tables_public == []


def test_sealing_identical_content_twice_is_idempotent_not_an_error(tmp_path):
    """Real bug found while building package persistence: package_id is
    a content-hash prefix, so sealing identical content twice (a real
    case — the same question asked twice) deterministically produces
    the same package_id. Persisting must be idempotent, not a bare
    INSERT (which raised a real sqlite3.IntegrityError before this was
    fixed in seal_evidence_package)."""
    engine, env_overrides, metric_key = _setup(tmp_path)
    pkg_a = seal_evidence_package("q", "internal", query="SKM-12", metric_keys=[metric_key], env_overrides=env_overrides)
    pkg_b = seal_evidence_package("q", "internal", query="SKM-12", metric_keys=[metric_key], env_overrides=env_overrides)
    assert pkg_a["package_id"] == pkg_b["package_id"]


def test_merge_and_replay_round_trip(tmp_path):
    engine, env_overrides, metric_key = _setup(tmp_path)
    pkg_a = seal_evidence_package("q1", "internal", metric_keys=[metric_key], env_overrides=env_overrides)
    pkg_b = seal_evidence_package("q2", "internal", metric_keys=[metric_key], env_overrides=env_overrides)

    merged = merge_packages([pkg_a["package_id"], pkg_b["package_id"]], "combined", "internal", env_overrides=env_overrides)
    assert len(merged["facts"]) == len(pkg_a["facts"]) + len(pkg_b["facts"])

    replayed = replay(pkg_a["package_id"], "internal", env_overrides=env_overrides)
    assert replayed["content_hash"] == pkg_a["content_hash"]


def test_replay_refuses_a_public_caller_reading_a_restricted_package(tmp_path):
    """The adversarial cache-correctness case replay() exists to
    prevent: a restricted package's package_id, replayed under a public
    persona, must be refused — not silently downgraded, not partially
    returned."""
    engine, env_overrides, metric_key = _setup(tmp_path)
    pkg = seal_evidence_package("q", "internal", metric_keys=[metric_key], env_overrides=env_overrides)
    try:
        replay(pkg["package_id"], "public", env_overrides=env_overrides)
        assert False, "expected AccessDenied"
    except Exception as e:
        assert "may not replay" in str(e)
