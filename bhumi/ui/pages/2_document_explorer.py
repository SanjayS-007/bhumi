"""The MVP-1 demo screen: pick a document, pick a table, pick a cell,
watch it get outlined on the actual source page with its resolved header
chain — the "unit was read, not guessed" moment.
"""
import json

import streamlit as st
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.read.headers import resolve_headers
from bhumi.storage.db.engine import make_engine
from bhumi.storage.db.models import DocumentAst, SourceRegistry

st.set_page_config(page_title="BHUMI — Document Explorer", layout="wide")
st.title("Document Explorer")

settings = get_settings()
engine = make_engine(settings)

with Session(engine) as session:
    docs = session.query(SourceRegistry).all()

if not docs:
    st.warning("No documents registered yet. Run `uv run task ingest -- --sample`.")
    st.stop()

doc_id = st.selectbox("Document", [d.doc_id for d in docs])

with Session(engine) as session:
    ast_row = session.get(DocumentAst, doc_id)

if not ast_row:
    st.error("No AST found for this document — read pipeline has not run.")
    st.stop()

ast = json.loads(open(ast_row.ast_path, encoding="utf-8").read())

if not ast["tables"]:
    st.info("No tables extracted for this document.")
    st.stop()

table_labels = [f"{t['element_id']} (page {t['page_no']}, {t['num_rows']}x{t['num_cols']})" for t in ast["tables"]]
table_idx = st.selectbox("Table", range(len(ast["tables"])), format_func=lambda i: table_labels[i])
table = ast["tables"][table_idx]

# reconstruct row-major text grid for header resolution
grid: list[list[str]] = [["" for _ in range(table["num_cols"])] for _ in range(table["num_rows"])]
cell_by_rc = {}
header_row_count = 0
for cell in table["cells"]:
    grid[cell["row"]][cell["col"]] = cell["text"]
    cell_by_rc[(cell["row"], cell["col"])] = cell
    if cell["column_header"]:
        header_row_count = max(header_row_count, cell["row"] + 1)

left, right = st.columns([1, 1])

with left:
    st.subheader("Reconstructed grid")
    st.dataframe(grid, use_container_width=True)

    data_rows = list(range(header_row_count, table["num_rows"]))
    if not data_rows:
        st.info("This table has no data rows below the detected header.")
        st.stop()
    row = st.selectbox("Row", data_rows, format_func=lambda r: f"row {r}: {grid[r][0]}")
    col = st.selectbox("Column", range(table["num_cols"]), format_func=lambda c: f"col {c}")

    cell = cell_by_rc.get((row, col))
    header_chain = resolve_headers(grid, header_row_count, col)

    st.markdown(f"**Value:** `{cell['text']}`")
    st.markdown(f"**Header chain:** {' › '.join(header_chain) if header_chain else '(none)'}")
    if cell["footnote_markers"]:
        st.markdown(f"**Footnote markers:** {', '.join(cell['footnote_markers'])}")
    st.code(
        f"{doc_id} · p.{table['page_no']} · {table['element_id']} · r{row}c{col} · "
        f"conf {table['confidence']} · tier {table['tier']}"
    )

with right:
    st.subheader(f"Source — page {table['page_no']}")
    page_info = next(p for p in ast["pages"] if p["page_no"] == table["page_no"])
    if not page_info["raster_path"]:
        st.warning("No raster available for this page.")
    else:
        img = Image.open(page_info["raster_path"]).convert("RGB")
        scale = img.width / page_info["width"]
        draw = ImageDraw.Draw(img)
        if cell.get("bbox"):
            b = cell["bbox"]
            draw.rectangle(
                [b["l"] * scale, b["t"] * scale, b["r"] * scale, b["b"] * scale],
                outline="red", width=3,
            )
        else:
            st.caption("No per-cell bbox recorded for this cell (blank cell).")
        st.image(img, use_container_width=True)
