"""Azure OpenAI implementations of the Reranker/EntailmentChecker/
NarrativeGenerator Protocols — the user's second key this session, after
the Gemini key turned out to be malformed (see PROVENANCE.md: Google's own
server returned `ACCESS_TOKEN_TYPE_UNSUPPORTED` for a raw REST call with
no SDK involved). This one is real: a live `chat.completions.create` call
against the `gpt-5.2-chat` deployment returned a real completion this
session.

**Not selected automatically over Gemini in select.py's preference
order — it's tried first now, since it's the only credential this session
that has actually produced a real model response.**

Real bug worked around here, not upstream: `pip-system-certs` (installed
ad-hoc into the venv for the earlier HF/Gemini network checks — see
PROVENANCE.md) globally monkeypatches `ssl.create_default_context` via
`truststore`. The `openai` SDK's own httpx client construction recurses
infinitely through that patched context (`RecursionError: maximum
recursion depth exceeded`) when pip-system-certs is active. Fixed by
building an explicit `httpx.Client` with a plain certifi-backed
`ssl.SSLContext` and passing it to `AzureOpenAI(http_client=...)` — Azure's
endpoint is signed by a public CA anyway, so certifi (not the Windows
trust store) is sufficient here, unlike pypi.org/generativelanguage on
this network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
from pathlib import Path

import certifi
import httpx
from dotenv import load_dotenv

from bhumi.models.protocols import DraftSentence, EntailmentVerdict, RankedPassage

REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")
USAGE_LOG = REPO_ROOT / "eval" / "runs" / "azure_usage.jsonl"
_CACHE: dict[str, object] = {}

_REQUIRED_ENV = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION")


class AzureOpenAIUnavailable(Exception):
    pass


def api_key_configured() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def _client():
    if not api_key_configured():
        raise AzureOpenAIUnavailable("AZURE_OPENAI_* env vars are not fully set")
    from openai import AzureOpenAI  # type: ignore

    # explicit certifi SSLContext, not the ambient (possibly
    # truststore-patched) default — see module docstring
    http_client = httpx.Client(verify=ssl.create_default_context(cafile=certifi.where()))
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        http_client=http_client,
    )


def _deployment() -> str:
    return os.environ.get("AZURE_OPENAI_TEXT_DEPLOYMENT") or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "")


model_name = _deployment


def _log_usage(purpose: str, usage) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(), "purpose": purpose, "model": _deployment(),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }) + "\n")


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _complete(client, prompt: str) -> tuple[str, object]:
    resp = client.chat.completions.create(
        model=_deployment(),
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=2000,
    )
    return resp.choices[0].message.content.strip(), resp.usage


class AzureOpenAIRerankerBackend:
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


class AzureOpenAIEntailmentBackend:
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


class AzureOpenAINarrativeBackend:
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
