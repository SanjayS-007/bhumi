"""The MVP-3 demo screen: pick a node, see its immediate neighbourhood
coloured by trust layer, click through to a supporting fact's source cell
(reusing Document Explorer's drill-down, not rebuilding it).
"""
import json

import streamlit as st
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.storage.db.engine import make_engine
from bhumi.storage.db.models import CandidateFactRow, DocumentAst, GraphEdge, GraphNode

st.set_page_config(page_title="BHUMI — Graph Explorer", layout="wide")
st.title("Graph Explorer")

settings = get_settings()
engine = make_engine(settings)

with Session(engine) as session:
    nodes = session.query(GraphNode).order_by(GraphNode.graph, GraphNode.label).all()

if not nodes:
    st.warning("No graph yet. Run `uv run task graph rebuild --doc-id <id>` (or ingest + assay a document first).")
    st.stop()

labels = [f"{n.node_id} ({n.graph}/{n.label})" for n in nodes]
idx = st.selectbox("Node", range(len(nodes)), format_func=lambda i: labels[i])
node = nodes[idx]

with Session(engine) as session:
    edges = session.query(GraphEdge).filter((GraphEdge.src == node.node_id) | (GraphEdge.dst == node.node_id)).all()

left, right = st.columns([1, 1])

TRUST_COLOR = {"authoritative": "🟩", "validated": "🟨", "derived": "⬜"}

with left:
    st.subheader(f"{node.label} · {node.node_id}")
    st.json(node.props)
    st.markdown(f"**{len(edges)} edge(s)**")
    for e in edges:
        other = e.dst if e.src == node.node_id else e.src
        arrow = "→" if e.src == node.node_id else "←"
        st.markdown(f"{TRUST_COLOR.get(e.trust_layer, '⬜')} `{e.trust_layer}` {arrow} **{e.rel}** {arrow} `{other}`"
                    + (f"  · fact `{e.fact_id}`" if e.fact_id else ""))

with right:
    fact_edges = [e for e in edges if e.fact_id]
    if not fact_edges:
        st.info("No supporting fact on this node's edges to drill into.")
    else:
        chosen = st.selectbox("Drill into a supporting fact", range(len(fact_edges)),
                               format_func=lambda i: f"{fact_edges[i].rel} · fact {fact_edges[i].fact_id}")
        e = fact_edges[chosen]
        doc_id = e.doc_id
        with Session(engine) as session:
            row = session.query(CandidateFactRow).filter(
                CandidateFactRow.doc_id == doc_id, CandidateFactRow.metric_key == e.props.get("metric_key"),
            ).first()
            ast_row = session.get(DocumentAst, doc_id) if doc_id else None
        if row and ast_row:
            ast = json.loads(open(ast_row.ast_path, encoding="utf-8").read())
            src = row.source
            page_info = next((p for p in ast["pages"] if p["page_no"] == src["page_no"]), None)
            st.code(f"{doc_id} · p.{src['page_no']} · {src['table_ref']} · {src['cell_ref']} · {row.value_raw}")
            if page_info and page_info["raster_path"]:
                img = Image.open(page_info["raster_path"]).convert("RGB")
                scale = img.width / page_info["width"]
                bbox = src.get("bbox")
                if bbox:
                    draw = ImageDraw.Draw(img)
                    draw.rectangle([bbox["l"] * scale, bbox["t"] * scale, bbox["r"] * scale, bbox["b"] * scale],
                                   outline="red", width=3)
                st.image(img, use_container_width=True)
        else:
            st.info("Source cell not resolvable for this edge (candidate row not found).")
