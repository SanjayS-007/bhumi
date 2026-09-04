# Classification decision — Marwatola I&II G2 GR

## 1. What was assigned, and why

`restricted`, assigned at registration on 2026-09-04 (`docs/
REAL_DOC_FINDINGS.md`). Reason: **not a judgment call about the content**
(coordinates, estimates) — the document's own page 1 carries a printed,
explicit restriction banner:

> *"STRICTLY RESTRICTED FOR COMPANY USE ONLY. THE INFORMATION GIVEN IN THIS
> REPORT IS NOT TO BE COMMUNICATED EITHER DIRECTLY OR INDIRECTLY TO THE
> PRESS OR ANY PERSON NOT HOLDING AN OFFICIAL POSITION IN THE CIL/
> GOVERNMENT."*

This is the author's (CMPDI's) own stated classification, printed in the
document. BHUMI didn't infer sensitivity from the content (coordinates,
resource figures) — it read the label the source already carries. That's a
narrower, more defensible basis than a content-based judgment call would
have been, and it's the one used here.

## 2. Is "publicly downloadable" the same as "classification: public"?

**No, and this session's finding says so explicitly, not as a footnote.**
NMET hosts this file at a URL reachable without authentication — that is a
fact about *hosting*, not about *classification*. The file itself declares
a restriction that contradicts unrestricted public use. A government
agency making a file reachable by URL is not the same act as that agency
releasing the file for unrestricted public distribution; the two can and
here do diverge.

**Recorded for `PROVENANCE.md`:** *"NMET hosts MARWATOLA_I&II_G2.pdf for
public download; BHUMI classifies it `restricted` because the document's
own page 1 carries an explicit CMPDI internal-distribution-only banner —
public hosting and public classification are not the same judgment, and
where they conflict, the document's own stated classification wins."*

## 3. What this means for the demo

The Marwatola GR **stays classified `restricted`** and is used only as an
internal accuracy/structure fixture (header resolution, domain typing,
Assay, graph construction against real data). It must never appear in a
demo video, screenshot, or any committed/exported artifact — enforced in
code (`src/bhumi/export/guard.py::assert_exportable`), not just by
discipline.

**A second document, unambiguously `public`, was acquired for anything
that needs to appear on camera or in a public artifact** — see below.
