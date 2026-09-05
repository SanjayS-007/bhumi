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

Current status (2026-09-06, continued): all of Phase 5 that's in scope is
now built: passage retrieval with contextual chunking (`knowledge/
chunking.py`, `knowledge/retrieval.py`, real FTS5, classification filtered
inside the query), backward lineage (`knowledge/lineage.py`), and a real
retrieval ablation (`eval/run_retrieval_ablation.py` — lexical 0.55 →
+prefix 1.00 → +parent-expansion 1.00 on 11 real hand-written questions,
see SESSION_REPORT.md for why prefix already dominates here). A minimal
BEDROCK broker (`bhumi/broker/`, exactly 6 tools, `Principal`/`authorize()`
classification gate, deterministically-sealed `EvidencePackage`) now
fronts two real consuming agents (PQ Desk, Report Engine) that are
statically proven (`tests/test_agents_use_broker_only.py`, AST-checked) to
never import storage/knowledge directly. Model backends are now an env-driven registry
(`models/backends/select.py`'s `_BACKENDS` table + `BHUMI_MODEL_BACKEND`
env var: unset/`auto` cascades Azure→Gemini→Groq→deterministic; a
specific name pins one). **Azure OpenAI is real and working** — a live
`gpt-5.2-chat` call and a full BEDROCK→PQ-Desk pipeline run both verified
this session (see PROVENANCE.md). Gemini's provided key is genuinely
invalid (`ACCESS_TOKEN_TYPE_UNSUPPORTED` from Google's own server,
verified two independent ways, including after a follow-up message
claiming otherwise — that claim was tested and falsified, not accepted).
Groq is real, capability-gated code with no key provided, correctly
unexecuted. Claude remains real but **never auto-selected** — the user's
plan is org-restricted. The general test suite forces the deterministic
backend (conftest autouse) so `pytest` stays free/offline/fast; live
backends are exercised only by `tests/test_live_backends.py`, opt-in per
test.

**BEDROCK is now a real MCP server** (`bhumi/broker/mcp_server.py`, stdio
transport, `mcp>=1.0,<2.0` — the 2.x SDK is a from-scratch API rewrite,
pinned below it deliberately), not just an in-process Python API. Both
agents (`pq_desk.py`, `report_engine.py`) are real MCP clients
(`bhumi/broker/mcp_client.py` is their only sanctioned import — enforced
by an AST check that now also forbids `broker.server`/`authz`/`package`
direct imports, not just storage/knowledge). A genuine multi-client
concurrent-isolation test passes (two real subprocess MCP sessions,
different personas, verified never to see each other's evidence) — the
first point in the project where that class of bug could even exist to
be caught. `bedrock://meta/tools` is a real MCP resource, versioned.
**Still NOT built**: SSE/HTTP transport (documented upgrade path, config
value, not implemented), a third real document, partial-failure
ingestion resilience, forward Revision Impact Trace, Trace Explorer UI,
administrative graph seeding, `derived`-trust-layer enforcement test,
`check_coverage` gate-failure reasons, `published_statement` schema, the
full `serve` self-healing sequence beyond doctor+migrate+launch, resource-
budget admission check. Full detail: `SESSION_REPORT.md`'s newest
addendum, `PROVENANCE.md`'s newest sections. 58 tests pass, 2 correctly
auto-skipped (no CUDA; no GROQ_API_KEY).

Prior status (MVP-0/1/2, steps 1–9 of the build order, step 12/CI not
started):
- `task doctor --strict`, `task profile`, `task migrate` (now real Alembic,
  see below), `task acquire`, `task ingest -- --sample`, `task ingest
  --doc-id <id> --pages "N-M"`, `task assay run/explain/reeval`, `task
  serve` all run and were verified against **both** the synthetic sample
  **and** a real 254-page CMPDI Geological Report (see `docs/
  REAL_DOC_FINDINGS.md`).
- `pytest -q` — 20 tests pass (provenance invariant, Decimal round-trip,
  header resolution incl. real-geometry fallback, Assay gate ordering/rule
  severities/confidence, and a reeval integration test that actually
  recovers a soft-rejected candidate after a simulated pack version bump).
  `ruff check .` clean.
- **Alembic is now real** (`alembic/`, one autogenerated initial revision,
  `render_as_batch=True`). `storage/db/engine.migrate()` runs `alembic
  upgrade head`. The earlier `create_all()` pragmatism is retired — see
  PROVENANCE.md's 2026-09-05 entries for why it flipped.
- **The confidence-model bug is fixed** (page routing quality vs per-cell
  extraction confidence were conflated — see PROVENANCE.md). The sample
  doc's review queue is empty now; a genuinely-blank-page fixture keeps the
  mechanism tested (`tests/test_review_queue.py`).
- **`resolve_headers()` is now real-geometry-based**, not text-position
  guessing, and has been verified against an actual government report's
  3-level ragged merged header (`tests/test_headers.py`, `docs/
  REAL_DOC_FINDINGS.md` §2).
- Domain pack (`domain/packs/geological_report.yaml`) has two table types:
  `seam_range_summary_table` (built against the real GR) and
  `seam_thickness_table` (this codebase's synthetic sample only — no real
  document has ever matched it; the pack says so explicitly).
- Tier 1 (PyMuPDF) is the only read tier and was sufficient for the entire
  real 254-page document checked (fully born-digital). Tier 2 (Docling)/
  Tier 3 (PaddleOCR-VL) remain correctly `UNAVAILABLE`, not faked.
- Vector/Text/Graph storage backends are still interface-only (Phase 5).
- **Known, named, NOT-fixed gaps** (see `docs/REAL_DOC_FINDINGS.md`): a real
  seam's data spans two grid rows (values + a borehole-reference row) — the
  reference row safely soft-rejects rather than crashing, but its info
  isn't captured; multi-page table continuation is unverified; unit
  extraction from non-parenthesized headers (`"k. cal/kg"`) is unverified;
  footnote-marker-to-text linking is unverified on real data.
- **This machine has `UV_PROJECT_ENVIRONMENT` permanently set** to an
  unrelated project's venv at the OS/user level — `doctor --strict` will
  report `strict_ok=False` here until the user fixes that themselves (the
  check is correct; don't weaken it to make this machine pass).

Next action: build the entity/qualifier support for the two-grid-row seam
record (docs/REAL_DOC_FINDINGS.md §9), then multi-page table continuation,
then CI (step 12).

## Corpus

One real Geological Report acquired: `MARWATOLA_I&II_G2.pdf` (CMPDI,
Marwatola Sector-I&II, Sohagpur Coalfield, G2 stage), fetched from the NMET
URL the design doc named. **Registered `--classification restricted`, not
public** — the file itself carries an internal-distribution-only banner
despite the URL being publicly reachable; see `docs/REAL_DOC_FINDINGS.md`.
It lives only in `data/vault/` (gitignored, content-addressed) — never
commit it. Its full 254-page GR was only ingested page-range-limited so far
(`--pages "14-19"`, the section containing seam-quality tables) — the full
document has not been run end to end through `ingest`/`assay` in one go.
MVP-0/1/2 demos otherwise run on `task ingest -- --sample`, which must
synthesize a multi-page PDF with a realistic two-level-header
seam-thickness table via PyMuPDF — zero external downloads, works fully
offline. Additional real GRs, if acquired, go in `data/vault/` the same way
with a `corpus.yaml` manifest (not yet created) — never assume more than
this one exists until confirmed.

## Where this session's decisions are recorded

`PROVENANCE.md` — append new entries there, don't just tell the user; that
file is the audit trail a judge or teammate reads.
