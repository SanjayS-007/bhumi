"""Tiny, safe rule interpreter over rulebook/rules/*.yaml. Deliberately not
a generic expression language — no eval(), no string-expression parsing.
Two rule shapes only: `range` (single-metric bound) and `pair` (cross-field
comparison via a small named-relation registry). Add a third shape here, in
Python, the day a real rule can't be expressed by these two — do not widen
this into an expression DSL speculatively.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from bhumi.schemas.core import CandidateFact

RELATIONS = {
    "le": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "ge": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "eq": lambda a, b: a == b,
    "high_ash_high_gcv_implausible": lambda a, b: not (a > 40 and b > 5500),
}


@dataclass
class GateResult:
    gate: str
    passed: bool
    reason: str = ""
    severity: str = "block"


@dataclass
class RuleFinding:
    rule_id: str
    candidate_id: str
    severity: str
    message: str


def load_rules(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]


def _qualifier_lookup(c: CandidateFact, key: str) -> str | None:
    if key.startswith("qualifiers."):
        return c.qualifiers.get(key.split(".", 1)[1])
    return getattr(c, key, None)


def evaluate_range_rules(candidates: list[CandidateFact], rules: list[dict]) -> dict[str, list[RuleFinding]]:
    findings: dict[str, list[RuleFinding]] = {c.candidate_id: [] for c in candidates}
    for rule in rules:
        if rule["type"] != "range":
            continue
        for c in candidates:
            if c.metric_key not in rule["applies_to"] or c.value is None:
                continue
            if not (rule["min"] <= c.value <= rule["max"]):
                msg = rule["message"].format(metric_key=c.metric_key, min=rule["min"], max=rule["max"], value=c.value)
                findings[c.candidate_id].append(RuleFinding(rule["id"], c.candidate_id, rule["severity"], msg))
    return findings


def evaluate_pair_rules(candidates: list[CandidateFact], rules: list[dict]) -> dict[str, list[RuleFinding]]:
    findings: dict[str, list[RuleFinding]] = {c.candidate_id: [] for c in candidates}
    by_metric: dict[str, list[CandidateFact]] = {}
    for c in candidates:
        by_metric.setdefault(c.metric_key, []).append(c)

    for rule in rules:
        if rule["type"] != "pair":
            continue
        relation = RELATIONS[rule["relation"]]
        for ca in by_metric.get(rule["metric_a"], []):
            if ca.value is None:
                continue
            for cb in by_metric.get(rule["metric_b"], []):
                if cb.value is None:
                    continue
                match_keys = rule["match_on"]
                if any(_qualifier_lookup(ca, k) != _qualifier_lookup(cb, k) for k in match_keys):
                    continue
                if not relation(float(ca.value), float(cb.value)):
                    msg = rule["message"].format(a_value=ca.value, b_value=cb.value, entity_id=ca.entity_id)
                    findings[ca.candidate_id].append(RuleFinding(rule["id"], ca.candidate_id, rule["severity"], msg))
    return findings
