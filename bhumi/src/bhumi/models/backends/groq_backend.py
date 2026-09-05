"""Groq implementation of the Reranker/EntailmentChecker/NarrativeGenerator
Protocols — no key provided this session, so this is a real, capability-
gated implementation that has never been executed here (same honesty
pattern as Tier 3's GPU gate, or Claude's missing key). Groq's API is
OpenAI-compatible, so this reuses the `openai` SDK against Groq's base
URL rather than pulling in a separate SDK for one extra backend.

Set `GROQ_API_KEY` (and optionally `GROQ_MODEL`, default below) to enable.
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
load_dotenv(REPO_ROOT / ".env")
USAGE_LOG = REPO_ROOT / "eval" / "runs" / "groq_usage.jsonl"
DEFAULT_MODEL = "llama-3.1-8b-instant"
_CACHE: dict[str, object] = {}


class GroqUnavailable(Exception):
    pass


def api_key_configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def _model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


model_name = _model


def _client():
    if not api_key_configured():
        raise GroqUnavailable("GROQ_API_KEY is not set")
    from openai import OpenAI  # type: ignore

    return OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")


def _log_usage(purpose: str, usage) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(), "purpose": purpose, "model": _model(),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }) + "\n")


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _complete(client, prompt: str) -> tuple[str, object]:
    resp = client.chat.completions.create(model=_model(), messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content.strip(), resp.usage


class GroqRerankerBackend:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]:
        key = _cache_key("rerank", query, json.dumps([c["chunk_id"] for c in candidates], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        listing = "\n".join(f"{i}: {c['raw_text'][:200]}" for i, c in enumerate(candidates))
        prompt = f"Query: {query}\n\nCandidates:\n{listing}\n\nReturn the indices of the {k} most relevant candidates, most relevant first, comma-separated, nothing else."
        text, usage = _complete(client, prompt)
        _log_usage("rerank", usage)
        order = [int(x) for x in text.strip().split(",") if x.strip().isdigit()]
        result = [RankedPassage(candidates[i]["chunk_id"], score=1.0 / (rank + 1), raw_text=candidates[i]["raw_text"])
                  for rank, i in enumerate(order) if i < len(candidates)]
        _CACHE[key] = result
        return result


class GroqEntailmentBackend:
    def check(self, claim: str, evidence: list[dict]) -> EntailmentVerdict:
        key = _cache_key("entailment", claim, json.dumps([e.get("chunk_id", "") for e in evidence], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        evidence_text = "\n".join(e.get("raw_text", "") for e in evidence)
        prompt = f"Claim: {claim}\n\nEvidence:\n{evidence_text}\n\nIs the claim entailed by the evidence? Answer 'YES: reason' or 'NO: reason'."
        text, usage = _complete(client, prompt)
        _log_usage("entailment", usage)
        result = EntailmentVerdict(entailed=text.upper().startswith("YES"), reason=text.split(":", 1)[-1].strip())
        _CACHE[key] = result
        return result


class GroqNarrativeBackend:
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]:
        key = _cache_key("narrative", section_title, json.dumps(figures, sort_keys=True, default=str))
        if key in _CACHE:
            return _CACHE[key]
        client = _client()
        figures_text = "\n".join(f"[{f['figure_id']}] {f['metric_key']} = {f['value']} {f.get('unit', '')}" for f in figures)
        prompt = f"Section: {section_title}\n\nFigures (cite ONLY by [figure_id], never restate the number without its bracketed ID):\n{figures_text}\n\nDraft 2-3 sentences."
        text, usage = _complete(client, prompt)
        _log_usage("narrative", usage)
        cited = re.findall(r"\[([^\]]+)\]", text)
        result = [DraftSentence(text=text, cited_figure_ids=cited)]
        _CACHE[key] = result
        return result
