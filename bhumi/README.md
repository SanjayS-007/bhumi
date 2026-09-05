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

## Model backends (rerank / entailment / narrative)

Fully env-driven, per capability — no code change needed to switch providers:

```powershell
uv run task models
```

```
┌────────────┬─────────┬──────────────┬────────────────────────┐
│ capability │ backend │ model        │ reason                 │
├────────────┼─────────┼──────────────┼────────────────────────┤
│ rerank     │ azure   │ gpt-5.2-chat │ default: auto-cascade  │
│ entailment │ azure   │ gpt-5.2-chat │ default: auto-cascade  │
│ narrative  │ azure   │ gpt-5.2-chat │ default: auto-cascade  │
└────────────┴─────────┴──────────────┴────────────────────────┘
```

`BHUMI_MODEL_BACKEND` sets the default for all three (`auto` cascades
Azure → Gemini → Groq → deterministic, skipping anything unconfigured).
`BHUMI_BACKEND_NARRATIVE` / `BHUMI_BACKEND_ENTAILMENT` / `BHUMI_BACKEND_RERANK`
override one capability at a time, e.g. `BHUMI_BACKEND_NARRATIVE=gemini`.
`deterministic` / `local` / `none` disables API calls entirely. Every
non-deterministic backend falls back automatically per call if it errors
(bad key, quota, network) — see `src/bhumi/models/backends/select.py`.

The Gemini key configured this session does not work — not a code bug:
a raw `curl` with zero SDK involved gets `401 ACCESS_TOKEN_TYPE_UNSUPPORTED`
from Google's own server on every call including `ListModels`, matching a
known Google-side issue with `AQ.`-prefixed AI Studio keys (see
`PROVENANCE.md`, 2026-09-05). Groq works in code but has no key configured
here. Azure is the only backend with a real, currently-working credential
on this machine, so it's first in the auto-cascade.
