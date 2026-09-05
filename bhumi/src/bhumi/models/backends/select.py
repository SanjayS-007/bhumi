"""The one place backend selection happens — calling code (agents,
retrieval) asks for `get_reranker()` etc. and never checks which provider
or API key is configured itself. This is what makes the backend-swap
test meaningful: swap here, nothing else changes.

Backend choice is env-driven, not hardcoded, at two levels:
  - `BHUMI_MODEL_BACKEND` — the default for every capability.
  - `BHUMI_BACKEND_NARRATIVE` / `BHUMI_BACKEND_ENTAILMENT` / `BHUMI_BACKEND_RERANK`
    — an optional per-capability override, checked first. Set
    `BHUMI_BACKEND_NARRATIVE=gemini` to force narrative drafting onto
    Gemini while everything else still follows `BHUMI_MODEL_BACKEND`.
    This is the whole mechanism — no code change is needed to move one
    capability to a different provider, only an env var.

Each of those variables accepts:
  - unset / "auto" (default): try each backend in `_BACKENDS` order,
    skipping any whose required env vars aren't set, falling back to the
    deterministic backend at the end of the chain.
  - a specific name ("azure" | "gemini" | "groq"): use only that backend
    (still falling back to deterministic if the call itself fails).
  - "deterministic" / "local" / "none": deterministic only, no API calls.

Run `uv run task models` to see exactly which backend and model name was
resolved for each capability, and why — this is the single place to look
instead of re-deriving it from env vars by hand.

**`_BACKENDS` is the full lookup table (all three, so an explicit
`BHUMI_MODEL_BACKEND=azure`/`BHUMI_BACKEND_<X>=azure` still works), but
the "auto" cascade is a SEPARATE, shorter list: `AUTO_CASCADE = ("groq",
"gemini")`.** Azure is deliberately excluded from the auto default per
Addon 5's local-first/no-Azure-by-default correction — real bug in the
previous version of this file, found by direct user challenge, not by
inspection: the first cut only had one list (`_BACKENDS`, Azure-first)
and used it for both explicit lookup and the "auto" default, so on this
org laptop (the only backend with a currently-working credential is
Azure) every capability silently defaulted to Azure with reason
"default: auto-cascade" — exactly the org-only dependency Addon 5 said
not to leave in place, and exactly what would break on a clone to a
machine with no Azure access. Fixed by splitting the two lists: `auto`
now only ever walks Groq then Gemini (falling back to deterministic),
and Azure is reachable only by explicit name — `task models` proves
this: unset env vars now resolve to `groq`/`gemini`/`deterministic`,
never `azure`, unless `BHUMI_MODEL_BACKEND=azure` or
`BHUMI_BACKEND_<X>=azure` is set on purpose.

Gemini's key is currently rejected by Google itself — verified via a raw
`curl` with zero SDK involved (`401 ACCESS_TOKEN_TYPE_UNSUPPORTED` on
every operation including a bare `ListModels`), root-caused to a known
Google-side bug with `AQ.`-prefixed AI Studio keys (see PROVENANCE.md,
2026-09-05) — kept in `AUTO_CASCADE` regardless, since a corrected key
needs no code change to start working. Groq has no key configured on
this machine; its backend is real, capability-gated code that has never
been executed here (same honesty pattern as Tier 3's GPU gate) — it is
first in `AUTO_CASCADE`, not last, precisely because it's the one real
chance of a working cloud path once a key is provided. Claude is
deliberately never in `_BACKENDS` — the user's Anthropic access is
org-restricted this session; the Claude backend classes remain in the
codebase for whenever that changes.

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
# Full lookup table -- used for an EXPLICIT BHUMI_MODEL_BACKEND=<name> /
# BHUMI_BACKEND_<CAPABILITY>=<name>. Azure is here so it still works as a
# deliberate manual override, but is NOT in AUTO_CASCADE below.
_BACKENDS = [
    ("azure", azure.api_key_configured, azure.AzureOpenAIRerankerBackend, azure.AzureOpenAIEntailmentBackend, azure.AzureOpenAINarrativeBackend),
    ("gemini", gemini.api_key_configured, gemini.GeminiRerankerBackend, gemini.GeminiEntailmentBackend, gemini.GeminiNarrativeBackend),
    ("groq", groq.api_key_configured, groq.GroqRerankerBackend, groq.GroqEntailmentBackend, groq.GroqNarrativeBackend),
]
_BACKENDS_BY_NAME = {b[0]: b for b in _BACKENDS}

# What "auto" (the default, no BHUMI_MODEL_BACKEND/BHUMI_BACKEND_<X> set)
# actually walks, in order. Azure is deliberately excluded -- it only
# works on the org-account laptop and must never be a silent default a
# clone onto a different machine (e.g. no Azure access) quietly relies
# on. Local-first per Addon 5 once a real local backend exists; today
# that's Groq then Gemini, both usable from a personal free-tier key.
AUTO_CASCADE = ("groq", "gemini")


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


# capability name -> (cls_index into _BACKENDS' tuple, Protocol method name)
CAPABILITIES = {
    "rerank": (0, "rerank"),
    "entailment": (1, "check"),
    "narrative": (2, "draft"),
}


def _capability_env(capability: str) -> str:
    """Per-capability override (`BHUMI_BACKEND_NARRATIVE` etc.) wins over
    the global `BHUMI_MODEL_BACKEND` default — this is the whole
    "narrative for fact -> gemini_key" mechanism, entirely env-driven."""
    per_capability = os.environ.get(f"BHUMI_BACKEND_{capability.upper()}")
    return (per_capability or os.environ.get("BHUMI_MODEL_BACKEND", "auto")).lower()


def _selected_backends(capability: str = "narrative") -> list[tuple]:
    forced = _capability_env(capability)
    if forced in ("deterministic", "local", "none"):
        return []
    if forced in ("", "auto"):
        return [_BACKENDS_BY_NAME[name] for name in AUTO_CASCADE if _BACKENDS_BY_NAME[name][1]()]
    if forced not in _BACKENDS_BY_NAME:
        return []
    return [_BACKENDS_BY_NAME[forced]]


def _build_chain(capability: str, deterministic):
    cls_index, method = CAPABILITIES[capability]
    chain = deterministic
    for _name, _configured, *classes in reversed(_selected_backends(capability)):
        chain = _FallbackWrapper(classes[cls_index](), chain, method)
    return chain


def get_reranker() -> Reranker:
    return _build_chain("rerank", DeterministicRerankerBackend())


def get_entailment_checker() -> EntailmentChecker:
    return _build_chain("entailment", DeterministicEntailmentBackend())


def get_narrative_generator() -> NarrativeGenerator:
    return _build_chain("narrative", DeterministicNarrativeBackend())


def api_key_configured() -> bool:
    """Kept for tests/backwards-compat: is any real (non-deterministic)
    backend currently selectable given BHUMI_MODEL_BACKEND and env vars?"""
    return bool(_selected_backends())


def resolve(capability: str) -> dict:
    """What `task models` prints: which backend (and model name) actually
    wins for this capability right now, and why — the single source of
    truth instead of re-deriving it from env vars by hand."""
    forced = _capability_env(capability)
    per_capability_var = f"BHUMI_BACKEND_{capability.upper()}"
    reason = (
        f"{per_capability_var}={forced}" if os.environ.get(per_capability_var)
        else f"BHUMI_MODEL_BACKEND={forced}" if os.environ.get("BHUMI_MODEL_BACKEND")
        else "default: auto-cascade"
    )
    chosen = _selected_backends(capability)
    if not chosen:
        return {"capability": capability, "backend": "deterministic", "model": "(no API, rule-based)", "reason": reason}
    name, _configured, *_classes = chosen[0]
    module = {"azure": azure, "gemini": gemini, "groq": groq}[name]
    return {"capability": capability, "backend": name, "model": module.model_name(), "reason": reason}
