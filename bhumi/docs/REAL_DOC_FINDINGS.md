# Real-document findings — Marwatola Sector-I & II, G2 (CMPDI)

Source: `MARWATOLA_I&II_G2.pdf`, fetched 2026-09-04 from
`https://nmet.gov.in/upload/uploadfiles/files/MARWATOLA_I&II_G2.pdf` (the
exact URL the design doc named). 254 pages, born-digital throughout.

**⚠️ Classification note, checked before anything else was done with it:**
Page 1 carries the banner *"STRICTLY RESTRICTED FOR COMPANY USE ONLY... NOT
TO BE COMMUNICATED EITHER DIRECTLY OR INDIRECTLY TO THE PRESS OR ANY PERSON
NOT HOLDING AN OFFICIAL POSITION IN THE CIL/GOVERNMENT."* Registered with
`--classification restricted`, not `public` — the design doc's assumption
that GRs are "publicly downloadable" describes the *URL's* accessibility,
not the document's actual internal classification. The file lives only in
`data/vault/` (gitignored, content-addressed) and is never committed. This
matters for anyone re-running this session: do not change its
classification to `public` without an actual authorization to do so.

## 1. Born-digital or scanned?

Every one of the 254 pages has a real text layer (checked programmatically:
0 pages under the no-text-layer threshold). No scanned pages, no rotated
pages, no aspect-ratio anomalies (fold-out plates). **Tier 1 (PyMuPDF)
handles this entire document — Tier 2 (Docling) is not needed for it.**
This is one real, specific document; it does not prove no CMPDI GR is ever
scanned.

## 2. Spanning headers: repeated text, or `col_span`? — THE FLAGGED RISK, CONFIRMED

The risk assessment was right, and understated if anything. Real spanning
headers put their text **once**, in the leftmost spanned cell, and leave
every other spanned column a true `None` in `table.extract()` — the exact
opposite of this codebase's synthetic sample generator's convention.

Worse than a simple 2-level span: real headers are **ragged** — different
columns' labels start at different header-row depths. Example (page 18,
1-indexed; `Range of Seam Thickness` has no row-1 sub-label but does have a
row-2 Min/Max; the Proximate Analysis group has both):

```
row0: Seam Name | Range of Seam Thickness | None | Range of Effective Thickness | None | Range of Proximate Analysis on 60% RH & 40oC | None×8 | Range of GCV in k. cal/kg | None | Grade Range | None
row1: None      | None                    | None | None                          | None | M%    | None | Ash%  | None | VM%   | None | FC%   | None | None                       | None | None        | None
row2: None       | Min | Max | Min | Max | Min | Max | Min | Max | Min | Max | Min | Max | Min | Max | Min | Max
row3: (blank spacer row)
```

**Fix applied:** `read/headers.py::resolve_headers()` now uses real per-cell
bounding boxes (PyMuPDF's `table.rows[r].cells`, which is `None` exactly
where a column is spanned away) to find, by geometry, which header cell
covers a given data column, instead of guessing from text position. Verified
against this exact real table — `docs`/this session's transcript shows the
correct 3-level chain reconstructed for all 17 columns, e.g. column 8 →
`["Range of Proximate Analysis on 60% RH & 40oC", "Ash%", "Max"]`. Both
conventions now work: a direct non-blank cell is used as-is (covers the
synthetic generator); a blank cell falls back to bbox-containment (covers
this real document). Tests: `tests/test_headers.py`.

## 3. Where do units appear?

**Never in the data cell itself** in any table found. Units live in the
header text, in parentheses or attached to a label: `"Range of Seam
Thickness (m)"`, `"Range of GCV in k. cal/kg"`, `"Ash%"` (no space, no
parens — attached to the label, not bracketed). The design doc's step-1
("explicit unit in the cell") essentially never fires for this document; a
real domain pack must lean on step 2/3 (header/spanning-header) and treat
`%` as a suffix pattern, not just a `(...)` pattern.  `units.py`'s regex
(`\(([^)]+)\)|(%)`) already covers the `%`-suffix case; not yet re-verified
against `"k. cal/kg"` (no parens either) — **flagging as unverified**, the
current pack targets this metric with a hardcoded `expect_unit` rather than
header extraction, which sidesteps the gap rather than closing it.

## 4. Borehole IDs — exact strings

Two series appear in this document, not the design doc's illustrative
`SKM-12` / `SGT-07` (those strings do not occur anywhere in this PDF —
almost certainly the design author's stylized composite example, not a
transcription):

- `CSM I&II-01` through at least `CSM I&II-15` (and higher) — the primary
  coring series for this block.
- `MSM-19`, `MSM-21`, `MSM-22`, ... `MSM-55` — a second series, seen
  cross-referenced against `CSM I&II-*` rows (e.g. `"CSM I&II-01 / MSM-19"`
  in the coordinates table), so `MSM-*` is likely an older/adjacent-block
  borehole being reused as a correlation point, not a separate naming
  convention for the same wells.

**Important extraction wrinkle:** PyMuPDF's text extraction embeds literal
`\n` inside these ID strings when the ID happens to wrap or sit near a line
break in the source PDF, e.g. `"CSM \nI&II-01"`. Header text already had
this problem (`"Seam\nName"`) and `headers.py::_clean()` collapses it — but
plain body/data cell text (`read/tiers/tier1_pymupdf.py`'s footnote/text
handling) did **not** collapse internal whitespace before this session's
fix. **Fixed** in this pass: all extracted cell text now collapses internal
whitespace the same way headers do. `domain/packs/geological_report.yaml`'s
borehole regex was updated to `CSM I&II` / `MSM` (not `SKM`/`SGT`, which
don't occur here).

## 5. Seam names — exact strings

Seen in headers/labels: `"Seam III Top"`-style names are NOT what's used
here either. The seam-range table (page 18-19) lists seam names directly in
its own `Seam Name` column (not yet cross-checked cell-by-cell against a
controlled vocabulary — deferred; the pack's `seam` entity regex is
unverified against this document's actual seam-name strings and should be
treated as provisional).

## 6. Footnote markers

`*` appears 8 times across the whole 254-page document — rare but real.
Not yet isolated to a specific table cell + linked footnote text in this
session (time-boxed); `footnotes.py`'s marker *detection* regex is
unmodified and should still fire correctly on a bare trailing `*`, but this
has only been exercised against the synthetic sample's footnote, not a real
one. Flagging as unverified rather than claiming it.

## 7. Merged cells, multi-page tables, rotated pages, fold-outs

- Merged cells: yes, extensively (see §2) — both horizontal (spanning
  headers) and what appears to be vertical merges (`Seam Name`'s column
  header, single cell, tall).
- Multi-page tables: **not investigated this session** — the borehole
  schedule/lithology-log tables (page 39 onward) are one table per borehole,
  which may itself continue across a page break for a deep hole. Flagging
  as unverified; the current pipeline treats each page independently and
  would silently produce two separate `TableElement`s for a table that
  continues onto the next page, with no `continues_from`/`continues_to`
  link. This is a known gap, not a claimed capability.
- Rotated pages / fold-out plates: none found in this 254-page document
  (checked programmatically — 0 rotated, 0 aspect-ratio anomalies).

## 8. Does Tier 1 handle it, or is Tier 2 required?

**Tier 1 (PyMuPDF) alone.** Ingested pages 14–19 end to end through the
real MVP-1/2 pipeline (`task ingest --doc-id GR-MARWATOLA-I-II-G2 --pages
14-19`): 6 pages, 6 tables extracted, all at `confidence 0.95` (clean
born-digital, grid-consistent, headers fully resolved), zero review-queue
entries. Docling was never invoked and is not needed for this document.

## 9. A seam's data spans TWO grid rows, not one

Discovered while inspecting real values: row N holds the seam name + its
Min/Max numbers; row N+1 holds the borehole ID(s) those numbers came from
(a reference/annotation row); row N+2 is a blank spacer; then the next seam
starts at N+3. E.g. rows 4/5/6 = seam `IV` (values / borehole refs / blank),
rows 7/8/9 = seam `IIIA`, etc.

**This was not specifically designed for, and it doesn't need to be for
MVP-2 to behave safely.** `domain/emit.py`'s per-row model naturally
degrades correctly here without modification: rows with a non-blank entity
(seam-name) cell emit candidates using that row's own values (correct); the
borehole-reference row has a blank entity cell, so `entity_id` resolves to
`None`, and Gate G2 (shape completeness) soft-rejects it with a clear
reason instead of silently fabricating a record. The borehole-reference
information is simply not captured as structured data yet — that's a real,
named gap (an enhancement for a later Phase 3 pass), not a crash or a wrong
answer.

## What this changes about Phase 3's domain pack

The design doc's illustrative row (`Seam III Top | BH SKM-12 | gross 3.42 m
| net 2.91 m | ash 34.2% | GCV 4180 kcal/kg | Grade G9`) **does not exist
anywhere in this real 254-page report** (confirmed by an exhaustive
table-content search of every table in the document for a `gross`+`net`
per-borehole row shape — zero matches). The real seam-quality tables in
this GR are **per-seam Min/Max range summaries** (page 18-19: Seam Name,
Range of Seam Thickness Min/Max, Range of Effective Thickness Min/Max,
Proximate Analysis M%/Ash%/VM%/FC% Min/Max, GCV range Min/Max, Grade range
Min/Max), not per-borehole rows with a single value per metric.

**`domain/packs/geological_report.yaml` was rebuilt around this real
structure** (`seam_range_summary_table`), with a `stat` qualifier
(`min`/`max`) instead of assuming one value per metric per row. The
original per-borehole `seam_thickness_table` type is kept *only* for this
codebase's own synthetic sample document — it is explicitly labeled in the
pack as modeling the synthetic generator, not a verified real-document
pattern, so nobody mistakes it for something checked against a real GR.

## Bottom line for Phase 3/4

Build against this document's real structure, not the design doc's
illustrative example. Where I could not verify something in the time
available (multi-page table continuation, footnote-to-text linking, seam-
name vocabulary, unit extraction from non-parenthesized headers), it is
listed above as unverified, not silently assumed to work.
