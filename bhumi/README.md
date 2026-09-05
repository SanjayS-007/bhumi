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
┌────────────┬─────────┬───────────────────────┬────────────────────────┐
│ capability │ backend │ model                 │ reason                 │
├────────────┼─────────┼───────────────────────┼────────────────────────┤
│ rerank     │ groq    │ llama-3.1-8b-instant  │ default: auto-cascade  │
│ entailment │ groq    │ llama-3.1-8b-instant  │ default: auto-cascade  │
│ narrative  │ groq    │ llama-3.1-8b-instant  │ default: auto-cascade  │
└────────────┴─────────┴───────────────────────┴────────────────────────┘
```

`BHUMI_MODEL_BACKEND` sets the default for all three (`auto` cascades
**Groq → Gemini → deterministic**, skipping anything unconfigured).
`BHUMI_BACKEND_NARRATIVE` / `BHUMI_BACKEND_ENTAILMENT` / `BHUMI_BACKEND_RERANK`
override one capability at a time, e.g. `BHUMI_BACKEND_NARRATIVE=gemini`.
`deterministic` / `local` / `none` disables API calls entirely. Every
non-deterministic backend falls back automatically per call if it errors
(bad key, quota, network) — see `src/bhumi/models/backends/select.py`.

**Azure is deliberately NOT in the default auto-cascade** — it only works
with an org account this repo won't have on a clone. It's still in the
codebase and selectable, but only by explicit override:
`BHUMI_MODEL_BACKEND=azure` or `BHUMI_BACKEND_NARRATIVE=azure`, etc.

**Groq supports multiple free-tier keys, round-robin, to stretch the free
quota**: set `GROQ_API_KEYS=key_one,key_two,...` (comma-separated) instead
of a single `GROQ_API_KEY` — every call advances to the next key, and a
real rate-limit (429) response retries once against a different key
before giving up. Add or remove keys any time, no code change.

**Current real status of each cloud backend, verified, not assumed**:
- **Groq**: real, capability-gated code, round-robin key rotation
  implemented and unit-verified. Not network-verified on the machine that
  built this — this org's Zscaler web proxy blocks `api.groq.com`
  outright (confirmed via a raw `curl`: `"Not allowed to browse
  Generative AI and ML Applications category"`, and independently via
  the actual SDK call: `openai.APIConnectionError`). Should work as-is on
  a network that doesn't block it, e.g. a personal laptop.
- **Gemini**: confirmed broken by Google, not by this code — a raw
  `curl` with zero SDK involved gets `401 ACCESS_TOKEN_TYPE_UNSUPPORTED`
  on every call including `ListModels`, matching a known, currently-open
  Google-side issue with `AQ.`-prefixed AI Studio keys (see
  `PROVENANCE.md`, 2026-09-05). Try a freshly-generated key if you hit
  this — some accounts still issue the older, working `AIzaSy...` format.
- **Azure**: the only backend that has produced a real, verified model
  response on this machine — but requires org access most clones won't
  have, so it's excluded from the default cascade on purpose.
