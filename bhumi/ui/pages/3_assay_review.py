"""The MVP-2 demo screen: a candidate fact, its gate-by-gate verdicts, and
the source cell outlined on the page (reusing Document Explorer's raster +
bbox-drawing pattern, not rebuilding it) — with Approve / Soft-reject
actions that actually persist.
"""
import json

import streamlit as st
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.knowledge.ledger import publish_fact
from bhumi.storage.db.engine import make_engine
from bhumi.storage.db.models import CandidateFactRow, DocumentAst

st.set_page_config(page_title="BHUMI — Assay Review", layout="wide")
st.title("Assay Review")

settings = get_settings()
engine = make_engine(settings)

with Session(engine) as session:
    doc_ids = [r[0] for r in session.query(CandidateFactRow.doc_id).distinct().all()]

if not doc_ids:
    st.warning("No candidates yet. Run `uv run task assay run --doc-id <id>` first.")
    st.stop()

doc_id = st.selectbox("Document", doc_ids)
state_filter = st.selectbox("Queue", ["pending_review", "soft_rejected", "auto_passed", "published", "rejected"])

with Session(engine) as session:
    rows = (
        session.query(CandidateFactRow)
        .filter_by(doc_id=doc_id, state=state_filter)
        .order_by(CandidateFactRow.confidence)  # uncertainty-first (design doc M4.6)
        .all()
    )

st.caption(f"{len(rows)} candidate(s) in `{state_filter}`, ordered by ascending confidence")
if not rows:
    st.stop()

labels = [f"{r.entity_id or r.entity_raw or '?'} · {r.metric_key} = {r.value_raw} · conf {r.confidence}" for r in rows]
idx = st.selectbox("Candidate", range(len(rows)), format_func=lambda i: labels[i])
row = rows[idx]

left, right = st.columns([1, 1])

with left:
    st.subheader(f"{row.entity_id or row.entity_raw} · {row.metric_key}")
    st.markdown(f"**Value:** `{row.value_raw}` {row.unit or ''}  ·  **state:** `{row.state}`")
    st.progress(min(1.0, row.confidence), text=f"confidence {row.confidence}")

    st.markdown("**Gates**")
    for g in row.gate_results:
        icon = "✅" if g["passed"] else "⚠️" if g["gate"] == "G5_deterministic_rules" and row.state != "soft_rejected" else "❌"
        st.markdown(f"{icon} `{g['gate']}` — {g['reason'] or 'ok'}")

    if row.failed_gate:
        st.error(f"Failed at {row.failed_gate}: {row.failure_reason}")

    st.markdown("**Source**")
    src = row.source
    st.code(f"{row.doc_id} · p.{src['page_no']} · {src['table_ref']} · {src['cell_ref']}")

    c1, c2, c3 = st.columns(3)
    if c1.button("Approve", disabled=row.state in ("published",)):
        with Session(engine) as session:
            r = session.get(CandidateFactRow, row.candidate_id)
            r.state = "published"
            r.approver = "reviewer_demo"
            session.commit()
            if r.entity_id and r.value is not None:  # categorical/unresolved-entity facts aren't ledger-eligible yet
                publish_fact(session, r, approver="reviewer_demo")
        st.rerun()
    if c2.button("Soft-reject", disabled=row.state == "soft_rejected"):
        with Session(engine) as session:
            r = session.get(CandidateFactRow, row.candidate_id)
            r.state = "soft_rejected"
            r.failure_reason = "manually soft-rejected by reviewer"
            session.commit()
        st.rerun()
    if c3.button("Reject", disabled=row.state == "rejected"):
        with Session(engine) as session:
            r = session.get(CandidateFactRow, row.candidate_id)
            r.state = "rejected"
            r.approver = "reviewer_demo"
            session.commit()
        st.rerun()

with right:
    st.subheader(f"Source — page {row.source['page_no']}")
    with Session(engine) as session:
        ast_row = session.get(DocumentAst, doc_id)
    ast = json.loads(open(ast_row.ast_path, encoding="utf-8").read())
    page_info = next((p for p in ast["pages"] if p["page_no"] == row.source["page_no"]), None)
    if not page_info or not page_info["raster_path"]:
        st.warning("No raster available for this page.")
    else:
        img = Image.open(page_info["raster_path"]).convert("RGB")
        scale = img.width / page_info["width"]
        bbox = row.source.get("bbox")
        if bbox:
            draw = ImageDraw.Draw(img)
            draw.rectangle(
                [bbox["l"] * scale, bbox["t"] * scale, bbox["r"] * scale, bbox["b"] * scale],
                outline="red", width=3,
            )
        st.image(img, use_container_width=True)
