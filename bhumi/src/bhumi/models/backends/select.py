"""The one place backend selection happens — calling code (agents,
retrieval) asks for `get_reranker()` etc. and never checks which provider
or API key is configured itself. This is what makes the backend-swap
test meaningful: swap here, nothing else changes.

Backend choice is env-driven (`BHUMI_MODEL_BACKEND`), not hardcoded:
  - unset / "auto" (default): try each backend in `_BACKENDS` order,
    skipping any whose required env vars aren't set, falling back to the
    deterministic backend at the end of the chain.
  - a specific name ("azure" | "gemini" | "groq"): use only that backend
    (still falling back to deterministic if the call itself fails).
  - "deterministic" / "local" / "none": deterministic only, no API calls.

`_BACKENDS` order = Azure OpenAI > Gemini > Groq. Azure is first because
it's the only credential this session that has actually produced a real
model response (a live `gpt-5.2-chat` completion, verified 2026-09-06).
The Gemini key provided this session is malformed — verified two
independent ways against Google's live server with zero SDK involved:
`?key=` query param and `x-goog-api-key` header both return
`401 ACCESS_TOKEN_TYPE_UNSUPPORTED` (see PROVENANCE.md) — kept in the
chain regardless, since a corrected key needs no code change to start
working. Groq has no key configured this session; its backend is real,
capability-gated code that has never been executed (same honesty pattern
as Tier 3's GPU gate). Claude is deliberately never in `_BACKENDS` — the
user's Anthropic access is org-restricted this session; the Claude
backend classes remain in the codebase for whenever that changes.

Every backend call is wrapped with a per-call fallback to the next one
down the chain, not just a presence check — a configured credential can
still fail at call time (blocked key, quota, transient network), which
only surfaces when the call is actually made.
"""
from __future__ import annotations

import os

import structlog

from bhumi.models.backends import azure_openai_backend as azure
from bhumi.models.backends import gemini_backend as gemini
from bhumi.models.backends import groq_backend as groq
from bhumi.models.backends.deterministic_backend import (
    DeterministicEntailmentBackend,
    DeterministicNarrativeBackend,
    DeterministicRerankerBackend,
)
from bhumi.models.protocols import EntailmentChecker, NarrativeGenerator, Reranker

log = structlog.get_logger()

# name -> (api_key_configured, RerankerCls, EntailmentCls, NarrativeCls)
_BACKENDS = [
    ("azure", azure.api_key_configured, azure.AzureOpenAIRerankerBackend, azure.AzureOpenAIEntailmentBackend, azure.AzureOpenAINarrativeBackend),
    ("gemini", gemini.api_key_configured, gemini.GeminiRerankerBackend, gemini.GeminiEntailmentBackend, gemini.GeminiNarrativeBackend),
    ("groq", groq.api_key_configured, groq.GroqRerankerBackend, groq.GroqEntailmentBackend, groq.GroqNarrativeBackend),
]


class _FallbackWrapper:
    """Try the primary backend; on ANY failure (network, auth, quota),
    fall back to the next backend and log why — never crash the calling
    agent because an external API had a bad day."""

    def __init__(self, primary, fallback, method: str):
        self._primary, self._fallback, self._method = primary, fallback, method

    def __getattr__(self, name):
        if name != self._method:
            return getattr(self._fallback, name)

        def call(*args, **kwargs):
            try:
                return getattr(self._primary, name)(*args, **kwargs)
            except Exception as e:
                log.warning("backend_fallback", backend=type(self._primary).__name__, method=name, error=str(e))
                return getattr(self._fallback, name)(*args, **kwargs)

        return call


def _selected_backends() -> list[tuple]:
    forced = os.environ.get("BHUMI_MODEL_BACKEND", "auto").lower()
    if forced in ("deterministic", "local", "none"):
        return []
    if forced in ("", "auto"):
        return [b for b in _BACKENDS if b[1]()]
    return [b for b in _BACKENDS if b[0] == forced]


def _build_chain(cls_index: int, method: str, deterministic):
    chain = deterministic
    for _name, _configured, *classes in reversed(_selected_backends()):
        chain = _FallbackWrapper(classes[cls_index](), chain, method)
    return chain


def get_reranker() -> Reranker:
    return _build_chain(0, "rerank", DeterministicRerankerBackend())


def get_entailment_checker() -> EntailmentChecker:
    return _build_chain(1, "check", DeterministicEntailmentBackend())


def get_narrative_generator() -> NarrativeGenerator:
    return _build_chain(2, "draft", DeterministicNarrativeBackend())


def api_key_configured() -> bool:
    """Kept for tests/backwards-compat: is any real (non-deterministic)
    backend currently selectable given BHUMI_MODEL_BACKEND and env vars?"""
    return bool(_selected_backends())
