"""Reranker/EntailmentChecker/NarrativeGenerator Protocols. One interface,
multiple backends (Claude, local-model-later, deterministic-fallback),
selected by config — never a scattered `if backend == "claude"` branch in
calling code. See tests/test_backend_agnostic.py for the proof."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RankedPassage:
    chunk_id: str
    score: float
    raw_text: str


@dataclass
class EntailmentVerdict:
    entailed: bool
    reason: str


@dataclass
class DraftSentence:
    text: str
    cited_figure_ids: list[str]


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[RankedPassage]: ...


class EntailmentChecker(Protocol):
    def check(self, claim: str, evidence: list[dict]) -> EntailmentVerdict: ...


class NarrativeGenerator(Protocol):
    def draft(self, section_title: str, figures: list[dict]) -> list[DraftSentence]: ...
