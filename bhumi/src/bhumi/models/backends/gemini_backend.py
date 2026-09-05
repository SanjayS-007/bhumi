"""Gemini-backed implementations of the Reranker/EntailmentChecker/
NarrativeGenerator Protocols — the user's preferred backend this session
(their Anthropic access is org-restricted; they provided a personal
Gemini free-tier key instead). Uses gemini-2.5-flash-lite, the current
lite/free-tier-friendly model as of this session (verified via
client.models.list() against the live API before being hardcoded here).

**Not executed this session past verification.** The key is real and
reaches generativelanguage.googleapis.com (confirmed: SSL/network fine
after the same pip-system-certs fix used for the earlier HF/Anthropic
checks), but every call returns
`401 UNAUTHENTICATED / API_KEY_SERVICE_BLOCKED` — Google recognizes the
key but has the Generative Language API blocked for whatever project it
belongs to. This looks like a Google Cloud Console key without that API
enabled, rather than an AI Studio key (https://aistudio.google.com/apikey)
minted directly for this API. See PROVENANCE.md 2026-09-06. The
deterministic fallback backend is what actually executes the agents this
session.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from bhumi.models.protocols import DraftSentence, EntailmentVerdict, RankedPassage

REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")  # GEMINI_API_KEY lives here, not in a BHUMI_-prefixed Settings field
USAGE_LOG = REPO_ROOT / "eval" / "runs" / "gemini_usage.jsonl"
MODEL = "gemini-2.5-flash-lite"
_CACHE: dict[str, object] = {}


class GeminiUnavailable(Exception):
    pass


def api_key_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _client():
    if not api_key_configured():
        raise GeminiUnavailable("GEMINI_API_KEY is not set")
    from google import genai  # type: ignore

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _log_usage(purpose: str, usage) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(), "purpose": purpose, "model": MODEL,
            "prompt_tokens": getattr(usage, "prompt_token_count", None),
            "candidates_tokens": getattr(usage, "candidates_token_count", None),
        }) + "\n")


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class GeminiRerankerBackend:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]:
        key = _cache_key("rerank", query, json.dumps([c["chunk_id"] for c in candidates], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        listing = "\n".join(f"{i}: {c['raw_text'][:200]}" for i, c in enumerate(candidates))
        resp = client.models.generate_content(
            model=MODEL,
            contents=f"Query: {query}\n\nCandidates:\n{listing}\n\nReturn the indices of the {k} most relevant candidates, most relevant first, comma-separated, nothing else.",
        )
        _log_usage("rerank", resp.usage_metadata)
        order = [int(x) for x in resp.text.strip().split(",") if x.strip().isdigit()]
        result = [RankedPassage(candidates[i]["chunk_id"], score=1.0 / (rank + 1), raw_text=candidates[i]["raw_text"])
                  for rank, i in enumerate(order) if i < len(candidates)]
        _CACHE[key] = result
        return result


class GeminiEntailmentBackend:
    def check(self, claim: str, evidence: list[dict]) -> EntailmentVerdict:
        key = _cache_key("entailment", claim, json.dumps([e.get("chunk_id", "") for e in evidence], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        evidence_text = "\n".join(e.get("raw_text", "") for e in evidence)
        resp = client.models.generate_content(
            model=MODEL,
            contents=f"Claim: {claim}\n\nEvidence:\n{evidence_text}\n\nIs the claim entailed by the evidence? Answer 'YES: reason' or 'NO: reason'.",
        )
        _log_usage("entailment", resp.usage_metadata)
        text = resp.text.strip()
        result = EntailmentVerdict(entailed=text.upper().startswith("YES"), reason=text.split(":", 1)[-1].strip())
        _CACHE[key] = result
        return result


class GeminiNarrativeBackend:
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]:
        key = _cache_key("narrative", section_title, json.dumps(figures, sort_keys=True, default=str))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        figures_text = "\n".join(f"[{f['figure_id']}] {f['metric_key']} = {f['value']} {f.get('unit', '')}" for f in figures)
        resp = client.models.generate_content(
            model=MODEL,
            contents=f"Section: {section_title}\n\nFigures (cite ONLY by [figure_id], never restate the number without its bracketed ID):\n{figures_text}\n\nDraft 2-3 sentences.",
        )
        _log_usage("narrative", resp.usage_metadata)
        text = resp.text.strip()
        cited = re.findall(r"\[([^\]]+)\]", text)
        result = [DraftSentence(text=text, cited_figure_ids=cited)]
        _CACHE[key] = result
        return result
