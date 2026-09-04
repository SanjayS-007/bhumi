# BHUMI — project instructions for Claude Code

BHUMI is a coal-sector document intelligence platform: ingest Indian government
geological/coal reports (PDFs), extract provenance-rich structured facts from
them, validate those facts against domain rules, and serve them through a
role-aware evidence broker (BEDROCK / MCP) to downstream AI agents. This is a
**hackathon submission** — working demo moments matter as much as code.

Full design context lives in two docs at the repo root of `2026/` (one level
up from `bhumi/`): `BHUMI_Data_Layer_Technical_Design.md.pdf` (the complete
Phase 0–7 design) and `compass_artifact_..._text_markdown.md` (tech-stack
research backing it). Read those before making an architectural call this
file doesn't cover.

## The situation — read this first

Build machine is a **locked-down Windows laptop**, verified 2026-09-04:
- No admin rights (confirmed: write to `Program Files` denied).
- No Docker.
- No CUDA GPU (Intel integrated graphics only — Tier-3 OCR and GPU torch are
  `UNAVAILABLE`, not `UNVERIFIED`).
- 15.5GB RAM, 264GB free disk.
- `git 2.53`, `uv` present (at `AppData\Roaming\Python\Python313\Scripts`,
  not the usual `.local\bin` — don't assume its path), system Python is 3.13
  at `C:\Program Files\Python313` — **do not use it directly**; always go
  through `uv`-managed Python 3.11.
- Code will later move to a workstation (RTX 4050 6GB VRAM, 24GB RAM, admin,
  Docker, local Postgres, GPU) — same codebase, switched by `BHUMI_PROFILE`.

## Non-negotiable rules

1. **One codebase, three profiles** (`sqlite` default, `supabase`,
   `workstation`), selected by `BHUMI_PROFILE` env var. Business logic never
   branches on which backend it's talking to — only `storage/factory.py`
   does. If you catch yourself writing `if profile == "sqlite"` outside that
   factory, stop and fix the interface instead.
2. **Never require Docker, admin rights, or a compiler.** Wheels only:
   `uv pip install --only-binary :all: ...`. A dependency with no Windows
   wheel is optional, in an `[project.optional-dependencies]` extra, and its
   absence degrades gracefully (log + skip a tier), never crashes.
3. **Never claim untested capability.** Anything that can't be verified on
   this machine goes in `ENVIRONMENT_REPORT.md` under *Unverified* with the
   exact command to verify later on the workstation. Don't write a mock that
   *looks* like real extraction — an honest `CapabilityUnavailable` beats a
   silent fake.
4. **`uv run task serve` is the one entry point.** It must run `doctor` +
   `migrate` + start the UI itself. Nobody should ever need to run three
   commands in the right order.
5. **Never break a working MVP.** MVP-1 must still work after every later
   commit. Commit after each build step in the order given below.
6. **No dialect-specific SQL in shared code.** No `JSONB`, no Postgres
   arrays, no `ON CONFLICT` raw SQL, no `pg_trgm` in code paths that must
   also run on SQLite. Use SQLAlchemy `JSON`, join tables, dialect-agnostic
   upsert, and a `Decimal`-as-`TEXT` `TypeDecorator` for exact numeric
   round-tripping (test `Decimal("3.42")` round-trips on both backends).
7. **`--offline` must actually work.** `task ingest -- --sample` and
   `task serve` must succeed with the network cable pulled. Never fetch
   during what could be a demo path.
8. **Don't add dependencies this doc's "deliberately not installing" list
   excludes** (LangChain, LlamaIndex, Great Expectations, Neo4j-as-default,
   OpenSearch, Airflow, Temporal) without discussing it first — each solves
   a problem this project doesn't have yet at this scale.
9. **Domain knowledge lives in YAML (`rulebook/`, `domain/packs/`), never in
   Python.** Adding a metric or table type should be a YAML/OKF diff, not a
   code change.
10. **Never hard-delete a candidate fact.** Soft-reject with a reason code;
    re-evaluate when a rule/pack/extraction/appeal changes. See Phase 4 state
    machine in the design doc.
11. **Model VRAM discipline, even on CPU-only right now.** Every model load
    goes through `runtime/model_slot.py`'s context manager. This matters
    less on this laptop (no GPU to protect) but the code must be identical
    on the workstation, so write it correctly from the start.
12. **400-line module limit.** Split before you exceed it.

## Build order (commit after each step, keep `task serve` runnable throughout)

1. `bootstrap.ps1` + `pyproject.toml` + lockfile + taskipy → `task --list` works
2. `env/probe.py` + `report.py` + `cli.py doctor` → writes `ENVIRONMENT_REPORT.md`
3. `config/settings.py` + `storage/factory.py` + `storage/interfaces.py` → `task profile` prints resolution
4. `storage/db` + SQLAlchemy models + `DecimalString` + Alembic → `task migrate` on SQLite
5. `storage/{blob,vector,text,graph}` + portability tests (SQLite path only for now)
6. `runtime/{model_slot,resources}` — write it right even though there's no GPU to test with yet
7. `acquire/` + `scripts/make_sample_pdf.py` → `task acquire`, `task ingest -- --sample`
8. `read/`: classifier → router → **Tier 1 (PyMuPDF) only** → normalise → raster — this alone must produce MVP-1, since Docling/Tier-2 CPU and Tier-3 are heavier/unavailable
9. `read/`: headers → footnotes → confidence → review queue → provenance-invariant test green
10. `read/tiers/tier2_docling.py` behind the `read` extra, `tier3_paddle.py` as a stub raising `CapabilityUnavailable`
11. `ui/`: corpus page → document explorer (drill-down demo) → read trace
12. CI (Windows + sqlite profile at minimum) + keep README/PROVENANCE current

Current status: **step 1 scaffolded** (`pyproject.toml`, `.env.example`,
`.gitattributes/.gitignore`, `scripts/bootstrap.ps1`, empty dir skeleton).
Nothing importable yet — `bhumi/src/bhumi/` has no code. Next action is
`env/probe.py` + `cli.py doctor`.

## Corpus

No real Geological Reports downloaded yet. MVP-0/1 work and demos run on
`task ingest -- --sample`, which must synthesize a multi-page PDF with a
realistic two-level-header seam-thickness table via PyMuPDF — zero external
downloads, works fully offline. When real NMET GRs (e.g. Marwatola I&II G2)
are added, they go in `data/vault/` (content-addressed, gitignored) with a
`corpus.yaml` manifest — never assume they exist until confirmed.

## Where this session's decisions are recorded

`PROVENANCE.md` — append new entries there, don't just tell the user; that
file is the audit trail a judge or teammate reads.
