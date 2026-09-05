"""Trace Explorer (kickoff §4.3): the full bidirectional chain from any
node — a real agent answer, a sealed package, a fact, a passage, a
candidate — back to a real source cell on a real scanned page, in one
screen. Reuses Document Explorer's raster+bbox drill-down, not rebuilt.
"""
import json

import streamlit as st
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.knowledge.lineage import trace_back_full
from bhumi.storage.db.engine import make_engine
from bhumi.storage.db.models import CandidateFactRow, DocumentAst, Fact, LineageEdge

st.set_page_config(page_title="BHUMI — Trace Explorer", layout="wide")
st.title("Trace Explorer")
st.caption("Follow any node — a fact, a sealed evidence package, an agent answer — back to its real source cell.")

settings = get_settings()
engine = make_engine(settings)

with Session(engine) as session:
    facts = session.query(Fact).filter(Fact.system_to.is_(None)).all()
    answer_ids = [row[0] for row in session.execute(
        select(LineageEdge.from_id).where(LineageEdge.from_kind == "answer").distinct()
    ).all()]

col1, col2 = st.columns(2)
with col1:
    start_kind = st.selectbox("Start from", ["fact", "answer", "package", "passage", "candidate"])
with col2:
    if start_kind == "fact" and facts:
        idx = st.selectbox("Fact", range(len(facts)), format_func=lambda i: f"{facts[i].metric_key} · {facts[i].entity_id} · {facts[i].fact_id[:12]}")
        start_id = facts[idx].fact_id
    elif start_kind == "answer" and answer_ids:
        start_id = st.selectbox("Answer", answer_ids)
    else:
        start_id = st.text_input("Node id", help="e.g. a package_id (SEP-...), passage chunk_id, or candidate_id")

if not start_id:
    st.info("No published facts/answers exist yet to pick from — enter a node id manually, or run the PQ Desk / Report Engine agents first.")
    st.stop()

with Session(engine) as session:
    graph = trace_back_full(session, start_kind, start_id)

st.subheader(f"{len(graph['nodes'])} node(s), {len(graph['edges'])} edge(s)")

KIND_ICON = {"answer": "🗨️", "package": "📦", "fact": "🧮", "passage": "📄", "candidate": "🔎", "cell": "🟥"}

left, right = st.columns([1, 1])
with left:
    st.markdown("**Chain**")
    for e in graph["edges"]:
        st.markdown(
            f"{KIND_ICON.get(e['from_kind'], '·')} `{e['from_kind']}:{e['from_id'][:24]}` "
            f"—{e['activity']}→ "
            f"{KIND_ICON.get(e['to_kind'], '·')} `{e['to_kind']}:{e['to_id'][:24]}`"
        )
    if not graph["edges"]:
        st.info("No lineage edges from this node — it may be a leaf (a source cell) or nothing has consumed it yet.")

with right:
    cell_nodes = [n for n in graph["nodes"] if n["kind"] == "cell"]
    candidate_nodes = [n for n in graph["nodes"] if n["kind"] == "candidate"]
    if not candidate_nodes:
        st.info("Trace doesn't reach a candidate/source cell from here.")
    else:
        chosen = st.selectbox("Drill into a reached candidate", range(len(candidate_nodes)),
                               format_func=lambda i: candidate_nodes[i]["id"])
        cid = candidate_nodes[chosen]["id"]
        with Session(engine) as session:
            row = session.get(CandidateFactRow, cid)
            ast_row = session.get(DocumentAst, row.doc_id) if row else None
        if row and ast_row:
            ast = json.loads(open(ast_row.ast_path, encoding="utf-8").read())
            src = row.source
            page_info = next((p for p in ast["pages"] if p["page_no"] == src["page_no"]), None)
            st.code(f"{row.doc_id} · p.{src['page_no']} · {src.get('table_ref', '')} · {src.get('cell_ref', '')} · {row.value_raw}")
            if page_info and page_info.get("raster_path"):
                img = Image.open(page_info["raster_path"]).convert("RGB")
                scale = img.width / page_info["width"]
                bbox = src.get("bbox")
                if bbox:
                    draw = ImageDraw.Draw(img)
                    draw.rectangle([bbox["l"] * scale, bbox["t"] * scale, bbox["r"] * scale, bbox["b"] * scale],
                                   outline="red", width=3)
                st.image(img, use_container_width=True)
        else:
            st.info("Candidate row not found for this trace node.")
