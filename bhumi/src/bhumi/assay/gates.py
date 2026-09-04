"""The seven gates (design doc M4.1), cheap-to-expensive. G6 (cross-document
conflict detection) is a documented no-op in MVP-2 — this corpus is a
single document, there is nothing to conflict with yet; Phase 5's Fact
Ledger is what makes G6 real."""
from __future__ import annotations

from dataclasses import dataclass

from bhumi.assay.confidence import compose_confidence
from bhumi.assay.rule_engine import RuleFinding
from bhumi.schemas.core import CandidateFact

AUTO_PASS_FLOOR = 0.85


@dataclass
class AssayVerdict:
    state: str  # auto_passed | pending_review | soft_rejected
    gate_results: list[dict]
    failed_gate: str | None
    failure_reason: str | None
    confidence: float


def run_gates(
    c: CandidateFact,
    findings: list[RuleFinding],
    known_metric_keys: set[str],
) -> AssayVerdict:
    results: list[dict] = []

    def rec(gate: str, passed: bool, reason: str = "") -> bool:
        results.append({"gate": gate, "passed": passed, "reason": reason})
        return passed

    has_value = c.value is not None or (c.value_raw and c.value_raw.strip())
    if not rec("G1_fact_worthiness", bool(c.metric_key) and bool(has_value)):
        return AssayVerdict("soft_rejected", results, "G1_fact_worthiness", "no metric/value bound to this cell", 0.0)

    is_decimal_metric = c.value is not None
    shape_ok = bool(c.entity_id) and bool(c.metric_key) and bool(has_value) and bool(c.period) and bool(c.status)
    if is_decimal_metric:
        shape_ok = shape_ok and bool(c.unit)
    if not rec("G2_shape_completeness", shape_ok):
        missing = [k for k, v in {
            "entity_id": c.entity_id, "unit": c.unit if is_decimal_metric else "n/a",
            "period": c.period, "status": c.status,
        }.items() if not v]
        return AssayVerdict("soft_rejected", results, "G2_shape_completeness", f"missing {missing}", 0.0)

    if not rec("G3_metric_binding", c.metric_key in known_metric_keys):
        return AssayVerdict("soft_rejected", results, "G3_metric_binding", f"'{c.metric_key}' not in Rule Book", 0.0)

    rec("G4_authority_check", True, "source authority_rank not modeled per-candidate in MVP-2")

    blocking = [f for f in findings if f.severity == "block"]
    warns = [f for f in findings if f.severity == "warn"]
    if not rec("G5_deterministic_rules", not blocking, "; ".join(f.message for f in blocking)):
        return AssayVerdict("soft_rejected", results, "G5_deterministic_rules", blocking[0].message, 0.0)
    if warns:
        results[-1]["reason"] = "; ".join(f.message for f in warns)

    rec("G6_conflict_detection", True, "no-op: single-document corpus, Phase 5 Fact Ledger needed for real cross-doc conflicts")

    confidence = compose_confidence(c.extraction_confidence, c.unit_source, bool(c.entity_id))
    state = "auto_passed" if (confidence >= AUTO_PASS_FLOOR and not warns) else "pending_review"
    rec("G7_risk_tiered_review", state == "auto_passed", f"confidence {confidence}, {len(warns)} warn(s)")

    return AssayVerdict(state, results, None, None, confidence)
