"""Graph build + invariants (design doc Phase 5.3/5.6). Uses the real
pipeline (read -> assay -> graph), not a hand-built fixture, so this is
exercised against genuine document structure."""
from pathlib import Path

from sqlalchemy.orm import Session

from bhumi.acquire.registry import register_local_file
from bhumi.assay.pipeline import run_assay
from bhumi.config.settings import Settings
from bhumi.domain.pack_loader import load_default_pack
from bhumi.knowledge.graph import multi_hop, neighbours, rebuild_graph_for_doc, seed_administrative_hierarchy
from bhumi.read.pipeline import run_read_pipeline
from bhumi.storage.db.engine import migrate
from bhumi.storage.db.models import DocumentAst, GraphEdge, GraphNode
from scripts.make_sample_pdf import make_sample_pdf


def _build(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, sqlite_path=tmp_path / "bhumi.db")
    engine = migrate(settings)
    sample_path = tmp_path / "sample.pdf"
    make_sample_pdf(sample_path)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, sample_path, doc_id="GRAPH-TEST", title="t",
            publisher="CMPDI", doc_kind="sample", authority_rank=2, stage="G2", coalfield="Sohagpur",
        )
        run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        ast_row = session.get(DocumentAst, row.doc_id)
        run_assay(session, row.doc_id, row.artifact_id, ast_row.ast_path, load_default_pack())
        rebuild_graph_for_doc(session, row.doc_id)
    return engine


def test_graph_has_all_three_trust_layers_present_where_expected(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        edges = session.query(GraphEdge).all()
        trust_layers = {e.trust_layer for e in edges}
        assert "authoritative" in trust_layers  # DESCRIBES/SUPPORTS, hand-seeded
        assert "validated" in trust_layers  # INTERSECTS/IN_BLOCK, assay-backed
        assert "derived" not in trust_layers  # not manufactured this session


def test_no_orphan_seam_every_seam_in_a_block(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        seams = session.query(GraphNode).filter_by(label="Seam").all()
        for seam in seams:
            in_block = session.query(GraphEdge).filter_by(src=seam.node_id, rel="IN_BLOCK").count()
            assert in_block >= 1, f"{seam.node_id} has no IN_BLOCK edge"


def test_no_intersects_edge_lacks_a_supporting_reference(tmp_path):
    """Every INTERSECTS edge must at least carry the metric_key it came
    from — a bare, unattributed edge is exactly what "derived, not
    manufactured" is meant to prevent."""
    engine = _build(tmp_path)
    with Session(engine) as session:
        edges = session.query(GraphEdge).filter_by(rel="INTERSECTS").all()
        assert edges  # the sample doc's boreholes must produce at least one
        for e in edges:
            assert e.props.get("metric_key")


def test_rebuild_is_idempotent_not_accumulating_duplicates(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        rebuild_graph_for_doc(session, "GRAPH-TEST")
        rebuild_graph_for_doc(session, "GRAPH-TEST")
        count_after_two_more_rebuilds = session.query(GraphEdge).filter_by(doc_id="GRAPH-TEST").count()
    with Session(engine) as session:
        rebuild_graph_for_doc(session, "GRAPH-TEST")
        count_after_one_more = session.query(GraphEdge).filter_by(doc_id="GRAPH-TEST").count()
    assert count_after_one_more == count_after_two_more_rebuilds


def test_multi_hop_query_borehole_to_block(tmp_path):
    """The query that justifies having a graph at all (design doc §2.3):
    which boreholes intersect which seams, and what block are those seams
    in — a 2-3 hop traversal a single table can't answer directly."""
    engine = _build(tmp_path)
    with Session(engine) as session:
        bh_nodes = session.query(GraphNode).filter_by(label="Borehole").all()
        assert bh_nodes
        start = bh_nodes[0].node_id
        paths = multi_hop(session, start, rels=["INTERSECTS", "IN_BLOCK"], max_hops=3)
        block_paths = [p for p in paths if p[-1].startswith("block:")]
        assert block_paths, "no path from a borehole to its block was found"


def test_neighbours_of_a_seam_includes_its_borehole(tmp_path):
    engine = _build(tmp_path)
    with Session(engine) as session:
        seam = session.query(GraphNode).filter_by(label="Seam").first()
        edges = neighbours(session, seam.node_id, rel="INTERSECTS")
        assert edges


def test_administrative_hierarchy_links_only_the_cmpdi_document(tmp_path):
    """kickoff §5.1: only CMPDI (a publicly, unambiguously verifiable CIL
    subsidiary) gets linked into a real hierarchy — no relationship is
    invented for publishers this session didn't independently verify."""
    engine = _build(tmp_path)
    with Session(engine) as session:
        result = seed_administrative_hierarchy(session)
        assert result["linked_documents"] == ["GRAPH-TEST"]  # the sample doc's publisher is CMPDI
        edge = session.query(GraphEdge).filter_by(src="document:GRAPH-TEST", rel="PUBLISHED_BY").one()
        assert edge.dst == "org:cmpdi"
        assert session.query(GraphEdge).filter_by(src="org:cmpdi", dst="org:cil").one().rel == "SUBSIDIARY_OF"


def test_derived_edges_never_appear_in_a_trust_filtered_traversal(tmp_path):
    """kickoff §5.2: the derived-trust enforcement guarantee, proven by
    construction with a real (test-only) derived edge inserted directly —
    zero derived edges exist in production data this session, but the
    filter mechanism itself must be verified BEFORE Topic Radar ever
    writes a real one."""
    engine = _build(tmp_path)
    with Session(engine) as session:
        seam = session.query(GraphNode).filter_by(label="Seam").first()
        # a fabricated derived edge to a node that exists nowhere else —
        # reachable ONLY through this one derived-trust edge
        session.add(GraphNode(node_id="topic:fake_similarity_cluster", label="Topic", graph="documentary", props={}))
        session.add(GraphEdge(src=seam.node_id, dst="topic:fake_similarity_cluster", rel="SIMILAR_TO", trust_layer="derived", props={}))
        session.commit()

        paths_all = multi_hop(session, seam.node_id, rels=["SIMILAR_TO"], max_hops=2, trust_layers=["authoritative", "validated", "derived"])
        assert any(p[-1] == "topic:fake_similarity_cluster" for p in paths_all)  # the mechanism itself works when allowed

        paths_trusted_only = multi_hop(session, seam.node_id, rels=["SIMILAR_TO"], max_hops=2, trust_layers=["authoritative", "validated"])
        assert not any(p[-1] == "topic:fake_similarity_cluster" for p in paths_trusted_only)
