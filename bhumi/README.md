# BHUMI

Coal-sector document intelligence — MVP-0 (foundation) + MVP-1 (read & drill-down).

See `CLAUDE.md` for the full operating rules, build order, and current status.

## Quickstart (this laptop: no admin, no Docker, no GPU)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
uv run task doctor          # writes ENVIRONMENT_REPORT.md
uv run task ingest -- --sample
uv run task serve           # opens http://localhost:8501
```

`ingest --sample` synthesizes a small multi-page PDF with a two-level-header
seam-thickness table (zero downloads) and runs it through the read pipeline.
`serve` opens a Streamlit app: **Corpus** (registered docs + read status) and
**Document Explorer** (pick a table cell, see it outlined on the source page
with its resolved header chain).

## What's real vs deferred

Tier-1 (PyMuPDF) read path only — this machine has no CUDA GPU, so Tier-2
(Docling) and Tier-3 (PaddleOCR-VL) are optional/unavailable. Vector/text/graph
search (Phase 5) are defined as interfaces but not implemented — MVP-1 doesn't
need retrieval, only extraction + drill-down. See `ENVIRONMENT_REPORT.md` for
the full honest capability table.
