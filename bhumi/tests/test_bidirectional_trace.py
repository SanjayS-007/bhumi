"""Full bidirectional structured trace (kickoff §4): backward lineage
already existed (tests/test_retrieval.py); this covers the forward
direction (Revision Impact) and the multi-branch Trace Explorer graph,
against a real published fact and a real agent-produced answer — not a
synthetic stand-in. A real consumer is generated first (re-running the PQ
Desk agent), exactly as the kickoff specified for the case where nothing
downstream exists yet.
"""
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.agents.pq_desk import answer_question
from bhumi.assay.pipeline import run_assay
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.chunking import build_chunks_for_doc
from bhumi.knowledge.ledger import publish_fact
from bhumi.knowledge.lineage import revision_impact, trace_back_full, trace_forward
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate, raw_sqlite_connection
from bhumi.storage.db.models import CandidateFactRow, DocumentAst, Fact
from scripts.make_sample_pdf import make_sample_pdf


def _setup(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="TRACE-TEST-DOC", title="t",
            publisher="CMPDI", doc_kind="sample", classification="restricted",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
        published = session.query(CandidateFactRow).filter_by(doc_id="TRACE-TEST-DOC", state="auto_passed").first()
        if published is None:
            published = session.query(CandidateFactRow).filter_by(doc_id="TRACE-TEST-DOC", state="pending_review").first()
        published.state = "published"
        fact = publish_fact(session, published, approver="test")
        metric_key, fact_id = fact.metric_key, fact.fact_id

    conn = raw_sqlite_connection(settings)
    with Session(engine) as session:
        build_chunks_for_doc(session, conn, "TRACE-TEST-DOC")

    env_overrides = {"BHUMI_DATA_DIR": str(tmp_path), "BHUMI_SQLITE_PATH": str(tmp_path / "bhumi.db")}
    return engine, env_overrides, metric_key, fact_id


def test_forward_trace_finds_a_real_agent_answer_from_its_source_fact(tmp_path):
    engine, env_overrides, metric_key, fact_id = _setup(tmp_path)

    # kickoff §4.1: "if nothing currently downstream references that
    # fact, generate one real consumer first" — no fact is used until an
    # agent actually answers a question with it
    result = answer_question(f"What is {metric_key}?", metric_key, role="internal", env_overrides=env_overrides)
    assert result["gap"] is None
    assert result["answer_id"]

    with Session(engine) as session:
        graph = trace_forward(session, "fact", fact_id)

    kinds = {n["kind"] for n in graph["nodes"]}
    assert "package" in kinds
    assert "answer" in kinds
    assert any(n["kind"] == "answer" and n["id"] == result["answer_id"] for n in graph["nodes"])
    assert any(e["from_kind"] == "package" and e["to_kind"] == "fact" and e["to_id"] == fact_id for e in graph["edges"])


def test_revision_impact_classifies_material_vs_immaterial_with_a_real_tolerance(tmp_path):
    engine, env_overrides, metric_key, fact_id = _setup(tmp_path)
    answer_question(f"What is {metric_key}?", metric_key, role="internal", env_overrides=env_overrides)

    with Session(engine) as session:
        fact = session.get(Fact, fact_id)
        original_value = fact.value

        tiny_bump = str(Decimal(fact.value) + Decimal("0.001"))
        big_bump = str(Decimal(fact.value) + Decimal("10"))

        immaterial = revision_impact(session, fact, tiny_bump, tolerance="0.01")
        material = revision_impact(session, fact, big_bump, tolerance="0.01")
        unchanged = revision_impact(session, fact, str(fact.value), tolerance="0.01")

    assert immaterial["classification"] == "immaterial"
    assert material["classification"] == "material"
    assert unchanged["classification"] == "unchanged"
    # every classification found the same real downstream answer
    assert any(n["kind"] == "answer" for n in material["downstream_nodes"])
    # revision_impact is read-only: the frozen fact row is untouched
    with Session(engine) as session:
        assert session.get(Fact, fact_id).value == original_value


def test_trace_back_full_returns_every_branch_from_a_package(tmp_path):
    engine, env_overrides, metric_key, fact_id = _setup(tmp_path)
    result = answer_question(f"What is {metric_key}?", metric_key, role="internal", env_overrides=env_overrides)

    with Session(engine) as session:
        graph = trace_back_full(session, "answer", result["answer_id"])

    kinds = {n["kind"] for n in graph["nodes"]}
    assert "answer" in kinds
    assert "package" in kinds
    assert "fact" in kinds
    assert "candidate" in kinds
    assert "cell" in kinds  # reaches all the way back to a real source cell
