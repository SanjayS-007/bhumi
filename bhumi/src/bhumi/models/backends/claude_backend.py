"""Claude-backed implementations of the Reranker/EntailmentChecker/
NarrativeGenerator Protocols (PROVENANCE.md 2026-09-06's pivot). Real
code against the Anthropic Python SDK — gated by a real capability check
(ANTHROPIC_API_KEY presence), exactly like Tier 3 is gated by CUDA
presence. **Not executed this session**: no key is configured in this
environment (verified: api.anthropic.com itself is fully reachable —
network is not the blocker, credentials are). Every call is cached by
content hash and logged to eval/runs/claude_usage.jsonl for cost tracking.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from bhumi.models.protocols import DraftSentence, EntailmentVerdict, RankedPassage

REPO_ROOT = Path(__file__).resolve().parents[4]
USAGE_LOG = REPO_ROOT / "eval" / "runs" / "claude_usage.jsonl"
_CACHE: dict[str, object] = {}


class ClaudeUnavailable(Exception):
    pass


def api_key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _client():
    if not api_key_configured():
        raise ClaudeUnavailable("ANTHROPIC_API_KEY is not set — network to api.anthropic.com is reachable, only the key is missing (verified 2026-09-06)")
    import anthropic  # type: ignore

    return anthropic.Anthropic()


def _log_usage(purpose: str, input_tokens: int, output_tokens: int) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(), "purpose": purpose,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        }) + "\n")


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class ClaudeRerankerBackend:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]:
        key = _cache_key("rerank", query, json.dumps([c["chunk_id"] for c in candidates], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        listing = "\n".join(f"{i}: {c['raw_text'][:200]}" for i, c in enumerate(candidates))
        resp = client.messages.create(
            model="claude-sonnet-5", max_tokens=200,
            messages=[{"role": "user", "content": f"Query: {query}\n\nCandidates:\n{listing}\n\nReturn the indices of the {k} most relevant candidates, most relevant first, comma-separated, nothing else."}],
        )
        _log_usage("rerank", resp.usage.input_tokens, resp.usage.output_tokens)
        order = [int(x) for x in resp.content[0].text.strip().split(",") if x.strip().isdigit()]
        result = [RankedPassage(candidates[i]["chunk_id"], score=1.0 / (rank + 1), raw_text=candidates[i]["raw_text"])
                  for rank, i in enumerate(order) if i < len(candidates)]
        _CACHE[key] = result
        return result


class ClaudeEntailmentBackend:
    def check(self, claim: str, evidence: list[dict]) -> EntailmentVerdict:
        key = _cache_key("entailment", claim, json.dumps([e.get("chunk_id", "") for e in evidence], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        evidence_text = "\n".join(e.get("raw_text", "") for e in evidence)
        resp = client.messages.create(
            model="claude-sonnet-5", max_tokens=150,
            messages=[{"role": "user", "content": f"Claim: {claim}\n\nEvidence:\n{evidence_text}\n\nIs the claim entailed by the evidence? Answer 'YES: reason' or 'NO: reason'."}],
        )
        _log_usage("entailment", resp.usage.input_tokens, resp.usage.output_tokens)
        text = resp.content[0].text.strip()
        result = EntailmentVerdict(entailed=text.upper().startswith("YES"), reason=text.split(":", 1)[-1].strip())
        _CACHE[key] = result
        return result


class ClaudeNarrativeBackend:
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]:
        key = _cache_key("narrative", section_title, json.dumps(figures, sort_keys=True, default=str))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        figures_text = "\n".join(f"[{f['figure_id']}] {f['metric_key']} = {f['value']} {f.get('unit', '')}" for f in figures)
        resp = client.messages.create(
            model="claude-sonnet-5", max_tokens=300,
            messages=[{"role": "user", "content": f"Section: {section_title}\n\nFigures (cite ONLY by [figure_id], never restate the number without its bracketed ID):\n{figures_text}\n\nDraft 2-3 sentences."}],
        )
        _log_usage("narrative", resp.usage.input_tokens, resp.usage.output_tokens)
        text = resp.content[0].text.strip()
        import re
        cited = re.findall(r"\[([^\]]+)\]", text)
        result = [DraftSentence(text=text, cited_figure_ids=cited)]
        _CACHE[key] = result
        return result
