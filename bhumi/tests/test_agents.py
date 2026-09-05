"""Both agents, end to end, against a real ingested/assayed/published
document — not a hand-built fixture. Covers kickoff §5's checklist items
8-10: one answerable question, one deliberately-unanswerable question,
persona boundary, and a report with a correctly-declared gap. Agents now
talk to BEDROCK over the real MCP stdio protocol (a subprocess per call),
not an in-process function call — env_overrides points that subprocess at
this test's isolated tmp_path DB instead of the real dev database.
"""
import asyncio
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bedrock_harness.pq_client import answer_question
from bedrock_harness.report_client import SectionSpec, generate_report
from bhumi.assay.pipeline import run_assay
from bhumi.broker.mcp_client import _call_tool_async, _list_tools_async
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.chunking import build_chunks_for_doc
from bhumi.knowledge.ledger import publish_fact
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate, raw_sqlite_connection
from bhumi.storage.db.models import CandidateFactRow, DocumentAst
from scripts.make_sample_pdf import make_sample_pdf


def _setup(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="AGENT-TEST-DOC", title="Agent test doc",
            publisher="CMPDI", doc_kind="sample", authority_rank=2, stage="G2", coalfield="Sohagpur",
            classification="restricted",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())

        published = session.query(CandidateFactRow).filter_by(doc_id="AGENT-TEST-DOC", state="auto_passed").first()
        if published is None:  # fall back to pending_review if nothing auto-passed
            published = session.query(CandidateFactRow).filter_by(doc_id="AGENT-TEST-DOC", state="pending_review").first()
        published.state = "published"
        fact = publish_fact(session, published, approver="test")
        real_metric_key = fact.metric_key

    conn = raw_sqlite_connection(settings)
    with Session(engine) as session:
        build_chunks_for_doc(session, conn, "AGENT-TEST-DOC")

    # every subsequent BEDROCK subprocess call must resolve to THIS
    # isolated tmp_path DB, not the real dev database
    env_overrides = {"BHUMI_DATA_DIR": str(tmp_path), "BHUMI_SQLITE_PATH": str(tmp_path / "bhumi.db")}
    return env_overrides, real_metric_key


def test_pq_agent_answers_a_real_answerable_question(tmp_path):
    env_overrides, metric_key = _setup(tmp_path)
    result = answer_question(f"What is {metric_key}?", metric_key, role="internal", env_overrides=env_overrides)
    assert result["gap"] is None
    assert result["answer"]
    assert result["figures"]


def test_pq_agent_declares_gap_for_unanswerable_question(tmp_path):
    env_overrides, _metric_key = _setup(tmp_path)
    result = answer_question("What is the stripping ratio?", "stripping_ratio", role="internal", env_overrides=env_overrides)
    assert result["gap"] is not None
    assert result["answer"] is None


def test_pq_agent_differs_by_persona_for_a_restricted_document(tmp_path):
    env_overrides, metric_key = _setup(tmp_path)
    answer_question("q", metric_key, role="internal", env_overrides=env_overrides)
    answer_question("q", metric_key, role="public", env_overrides=env_overrides)

    seal_args = {"intent": "q", "query": "SKM-12", "metric_keys": [metric_key]}

    async def _seal_both():
        return await asyncio.gather(
            _call_tool_async("seal_evidence_package", seal_args, "internal", env_overrides),
            _call_tool_async("seal_evidence_package", seal_args, "public", env_overrides),
        )

    pkg_internal, pkg_public = asyncio.run(_seal_both())
    assert pkg_internal["content_hash"] != pkg_public["content_hash"]
    assert pkg_internal["passages"] and not pkg_public["passages"]


def test_multi_client_isolation_two_concurrent_mcp_sessions(tmp_path):
    """kickoff §2.4: the thing last session's in-process design could not
    test even in principle — two real, concurrent MCP client sessions
    with different Principals hitting the same tool at the same time must
    never see each other's evidence or tool list. Concurrency is real
    (asyncio.gather over two live subprocesses), not simulated sequentially.
    """
    env_overrides, metric_key = _setup(tmp_path)

    async def run_both():
        return await asyncio.gather(
            _list_tools_async("public", env_overrides),
            _list_tools_async("internal", env_overrides),
            _call_tool_async("search_evidence", {"query": "SKM-12", "k": 5}, "public", env_overrides),
            _call_tool_async("search_evidence", {"query": "SKM-12", "k": 5}, "internal", env_overrides),
        )

    public_tools, internal_tools, public_hits, internal_hits = asyncio.run(run_both())
    # today both personas share the same TOOLS scope, so the tool LISTS
    # are identical — the isolation property under test is evidence
    # content, not tool visibility (which would differ if a future
    # persona had a narrower scope)
    assert set(public_tools) == set(internal_tools)
    assert internal_hits and not public_hits  # restricted doc's passages never reach the public session


def test_report_agent_declares_a_gap_for_an_uncovered_section(tmp_path):
    env_overrides, metric_key = _setup(tmp_path)
    report = generate_report("Test Report", [
        SectionSpec(title="Covered Metric", metric_key=metric_key),
        SectionSpec(title="Uncovered Metric", metric_key="stripping_ratio"),
    ], role="internal", env_overrides=env_overrides)
    gaps = [s for s in report["sections"] if s["gap"]]
    covered = [s for s in report["sections"] if not s["gap"]]
    assert gaps and any(s["title"] == "Uncovered Metric" for s in gaps)
    assert covered
