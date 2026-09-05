"""Minimal BEDROCK authorization — exactly the two personas this
session's PQ Desk / Report Engine agents need, per the kickoff prompt's
explicit scoping: not the full role surface from the base design yet.
"""
from __future__ import annotations

from dataclasses import dataclass

TOOLS = {"search_evidence", "get_fact", "compute_metric", "get_provenance", "check_coverage", "seal_evidence_package"}


@dataclass(frozen=True)
class Principal:
    subject: str
    max_classification: list[str]  # what this principal may ever see, e.g. ["public"]
    scopes: frozenset[str]


PUBLIC_CALLER = Principal(subject="public_caller", max_classification=["public"], scopes=frozenset(TOOLS))
INTERNAL_REVIEWER = Principal(subject="internal_reviewer", max_classification=["public", "restricted"], scopes=frozenset(TOOLS))


class AccessDenied(Exception):
    pass


def authorize(principal: Principal, tool: str) -> None:
    if tool not in principal.scopes:
        raise AccessDenied(f"{principal.subject} may not call {tool}")
