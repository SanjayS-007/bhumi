"""No-LLM fallback so the PQ Desk / Report Engine agents can run
end-to-end this session without ANTHROPIC_API_KEY. Deliberately weaker
than the Claude backend and labeled as such everywhere it's used:
- Rerank: FTS5's own bm25 order (already the input order — a no-op pass).
- Entailment: a presence check only (does every number/id in the claim
  literally appear in the evidence text?), not real language-level
  entailment.
- Narrative: a template, not generated prose.
Selecting this over the Claude backend is a config/availability decision,
never a silent code branch — see bhumi/models/backends/select.py.
"""
from __future__ import annotations

import re

from bhumi.models.protocols import DraftSentence, EntailmentVerdict, RankedPassage


class DeterministicRerankerBackend:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]:
        return [RankedPassage(c["chunk_id"], score=c.get("score", 0.0), raw_text=c["raw_text"]) for c in candidates[:k]]


class DeterministicEntailmentBackend:
    def check(self, claim: str, evidence: list[dict]) -> EntailmentVerdict:
        evidence_text = " ".join(e.get("raw_text", "") for e in evidence)
        # strip bracketed figure-id citations first — "[F1]" contains a
        # digit that isn't a claimed value, it's a reference.
        claim_without_citations = re.sub(r"\[[^\]]*\]", "", claim)
        numbers_in_claim = re.findall(r"\d+(?:\.\d+)?", claim_without_citations)
        missing = [n for n in numbers_in_claim if n not in evidence_text]
        if missing:
            return EntailmentVerdict(entailed=False, reason=f"claim cites {missing} not found verbatim in evidence (presence-check only, not real entailment)")
        return EntailmentVerdict(entailed=True, reason="every number in the claim appears in the evidence text (presence-check only, not real entailment)")


class DeterministicNarrativeBackend:
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]:
        if not figures:
            return [DraftSentence(text=f"{section_title}: no covered figures for this section.", cited_figure_ids=[])]
        parts = [f"{f['metric_key']} is {f['value']} {f.get('unit', '')} [{f['figure_id']}]".strip() for f in figures]
        text = f"{section_title}: " + "; ".join(parts) + "."
        return [DraftSentence(text=text, cited_figure_ids=[f["figure_id"] for f in figures])]
