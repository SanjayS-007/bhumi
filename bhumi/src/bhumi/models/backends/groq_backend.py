"""Groq implementation of the Reranker/EntailmentChecker/NarrativeGenerator
Protocols. Groq's API is OpenAI-compatible, so this reuses the `openai`
SDK against Groq's base URL rather than pulling in a separate SDK for
one extra backend.

**Confirmed untestable on this machine, and this is a network finding,
not a key or code problem**: a raw `curl` to `api.groq.com` (zero SDK)
is blocked outright by this org's Zscaler proxy — "Not allowed to browse
Generative AI and ML Applications category" — before any auth/API logic
ever runs. Same class of finding as the earlier GitHub Actions
`startup_failure` diagnosis: verified via the isolating test itself, not
assumed. Real capability-gated code, correctly unexecuted here, same
honesty pattern as Tier 3's GPU gate. Should work as-is wherever this
runs on a network that doesn't block it (e.g. the personal laptop).

Set `GROQ_API_KEY` for a single key, or `GROQ_API_KEYS` (comma-separated)
for several — several free-tier accounts' keys round-robin across calls
to spread the shared free-tier rate/day limit, and a call that hits a
rate limit (429) retries once against the next key before giving up.
"""
from __future__ import annotations

import hashlib
import itertools
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
# ponytail: module-level round-robin cursor, no lock -- this backend is
# called sequentially in this codebase (one subprocess per MCP call);
# add a lock if a future caller ever fans out concurrent Groq calls.
_KEY_CURSOR: itertools.cycle | None = None


def _api_keys() -> list[str]:
    multi = os.environ.get("GROQ_API_KEYS", "")
    if multi.strip():
        return [k.strip() for k in multi.split(",") if k.strip()]
    single = os.environ.get("GROQ_API_KEY", "")
    return [single] if single else []


def api_key_configured() -> bool:
    return bool(_api_keys())


def _model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


model_name = _model


class GroqUnavailable(Exception):
    pass


def _next_key() -> str:
    global _KEY_CURSOR
    keys = _api_keys()
    if not keys:
        raise GroqUnavailable("neither GROQ_API_KEY nor GROQ_API_KEYS is set")
    if _KEY_CURSOR is None:
        _KEY_CURSOR = itertools.cycle(keys)
    return next(_KEY_CURSOR)


def _client(api_key: str | None = None):
    from openai import OpenAI  # type: ignore

    return OpenAI(api_key=api_key or _next_key(), base_url="https://api.groq.com/openai/v1")


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


def _complete(prompt: str) -> tuple[str, object]:
    """Round-robins to the next key on every call; on a real rate-limit
    (429) response, retries once against a different key before raising
    (unless there's only one key, in which case it just raises)."""
    from openai import RateLimitError  # type: ignore

    for attempt in range(len(_api_keys())):
        try:
            resp = _client().chat.completions.create(model=_model(), messages=[{"role": "user", "content": prompt}])
            return resp.choices[0].message.content.strip(), resp.usage
        except RateLimitError:
            if attempt == len(_api_keys()) - 1:
                raise
    raise GroqUnavailable("no Groq keys configured")


class GroqRerankerBackend:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]:
        key = _cache_key("rerank", query, json.dumps([c["chunk_id"] for c in candidates], sort_keys=True))
        if key in _CACHE:
            return _CACHE[key]
        listing = "\n".join(f"{i}: {c['raw_text'][:200]}" for i, c in enumerate(candidates))
        prompt = f"Query: {query}\n\nCandidates:\n{listing}\n\nReturn the indices of the {k} most relevant candidates, most relevant first, comma-separated, nothing else."
        text, usage = _complete(prompt)
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
        evidence_text = "\n".join(e.get("raw_text", "") for e in evidence)
        prompt = f"Claim: {claim}\n\nEvidence:\n{evidence_text}\n\nIs the claim entailed by the evidence? Answer 'YES: reason' or 'NO: reason'."
        text, usage = _complete(prompt)
        _log_usage("entailment", usage)
        result = EntailmentVerdict(entailed=text.upper().startswith("YES"), reason=text.split(":", 1)[-1].strip())
        _CACHE[key] = result
        return result


class GroqNarrativeBackend:
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]:
        key = _cache_key("narrative", section_title, json.dumps(figures, sort_keys=True, default=str))
        if key in _CACHE:
            return _CACHE[key]
        figures_text = "\n".join(f"[{f['figure_id']}] {f['metric_key']} = {f['value']} {f.get('unit', '')}" for f in figures)
        prompt = f"Section: {section_title}\n\nFigures (cite ONLY by [figure_id], never restate the number without its bracketed ID):\n{figures_text}\n\nDraft 2-3 sentences."
        text, usage = _complete(prompt)
        _log_usage("narrative", usage)
        cited = re.findall(r"\[([^\]]+)\]", text)
        result = [DraftSentence(text=text, cited_figure_ids=cited)]
        _CACHE[key] = result
        return result
