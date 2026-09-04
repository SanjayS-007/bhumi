import streamlit as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.storage.db.engine import make_engine

st.set_page_config(page_title="BHUMI — Corpus", layout="wide")
st.title("Corpus")

settings = get_settings()
engine = make_engine(settings)

with Session(engine) as session:
    rows = session.execute(
        text(
            """
            SELECT r.doc_id, r.publisher, r.doc_kind, r.page_count, r.stage, r.coalfield,
                   a.table_count, a.element_count, a.ast_hash,
                   run.tier_counts, run.duration_s
            FROM source_registry r
            LEFT JOIN document_ast a ON a.doc_id = r.doc_id
            LEFT JOIN (
                SELECT doc_id, tier_counts, duration_s,
                       ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY started_at DESC) rn
                FROM read_run
            ) run ON run.doc_id = r.doc_id AND run.rn = 1
            """
        )
    ).mappings().all()

    review_counts = dict(
        session.execute(text("SELECT doc_id, COUNT(*) FROM review_queue GROUP BY doc_id")).all()
    )

if not rows:
    st.warning("No documents registered yet. Run `uv run task ingest -- --sample`.")
else:
    for r in rows:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.markdown(f"**{r['doc_id']}**  \n{r['publisher']} · {r['doc_kind']} · {r['stage'] or '—'} · {r['coalfield'] or '—'}")
            c2.markdown(
                f"pages: {r['page_count']} · tables: {r['table_count'] or 0} · elements: {r['element_count'] or 0}  \n"
                f"tier distribution: `{r['tier_counts']}`"
            )
            n_review = review_counts.get(r["doc_id"], 0)
            if n_review:
                c3.warning(f"{n_review} flagged for review")
            else:
                c3.success("0 flagged")
