"""Phase 4 (Assay) tests: gate ordering, rule severities, weakest-link
confidence, and the reeval recovery loop — the acceptance criteria in the
MVP-2 kickoff prompt (§4.9)."""
from decimal import Decimal

from bhumi.assay.confidence import compose_confidence
from bhumi.assay.gates import run_gates
from bhumi.assay.rule_engine import evaluate_pair_rules, evaluate_range_rules
from bhumi.schemas.core import BBox, CandidateFact, SourceRef

RULES = [
    {"id": "thickness_range", "type": "range", "applies_to": ["seam_thickness_gross", "seam_thickness_net"],
     "min": 0, "max": 50, "severity": "block", "message": "{metric_key} out of range (got {value})"},
    {"id": "net_le_gross", "type": "pair", "metric_a": "seam_thickness_net", "metric_b": "seam_thickness_gross",
     "relation": "le", "match_on": ["entity_id"], "severity": "block",
     "message": "net {a_value} > gross {b_value} for {entity_id}"},
    {"id": "ash_gcv_inverse", "type": "pair", "metric_a": "coal_ash_pct", "metric_b": "coal_gcv",
     "relation": "high_ash_high_gcv_implausible", "match_on": ["entity_id"], "severity": "warn",
     "message": "unusual ash/gcv for {entity_id}"},
]
KNOWN_METRICS = {"seam_thickness_gross", "seam_thickness_net", "coal_ash_pct", "coal_gcv"}


def _fact(**kw) -> CandidateFact:
    defaults = dict(
        candidate_id="c1", entity_raw="BH-1", entity_id="BH-1", metric_raw="x",
        value_raw="1", value=Decimal("1"), unit="m", unit_source="column_header:x",
        period="p", status="final",
        source=SourceRef(artifact_id="a", doc_id="d", page_no=1, element_id="e",
                         bbox=BBox(page_no=1, l=0, t=0, r=1, b=1)),
        extraction_confidence=0.95, domain_type="t",
    )
    defaults.update(kw)
    return CandidateFact(**defaults)


def test_gate_order_stops_at_g2_missing_unit_never_reaches_g5():
    c = _fact(candidate_id="c1", metric_key="seam_thickness_gross", unit=None, unit_source=None)
    verdict = run_gates(c, [], KNOWN_METRICS)
    assert verdict.state == "soft_rejected"
    assert verdict.failed_gate == "G2_shape_completeness"
    gates_run = [g["gate"] for g in verdict.gate_results]
    assert "G5_deterministic_rules" not in gates_run


def test_range_rule_blocks_out_of_range_value():
    c = _fact(candidate_id="c2", metric_key="seam_thickness_gross", value=Decimal("999"), value_raw="999")
    findings = evaluate_range_rules([c], RULES)[c.candidate_id]
    assert findings and findings[0].severity == "block"
    verdict = run_gates(c, findings, KNOWN_METRICS)
    assert verdict.state == "soft_rejected"
    assert verdict.failed_gate == "G5_deterministic_rules"


def test_pair_rule_blocks_net_greater_than_gross():
    net = _fact(candidate_id="net1", entity_id="BH-1", metric_key="seam_thickness_net", value=Decimal("5"))
    gross = _fact(candidate_id="gross1", entity_id="BH-1", metric_key="seam_thickness_gross", value=Decimal("3"))
    findings = evaluate_pair_rules([net, gross], RULES)
    assert findings[net.candidate_id]
    verdict = run_gates(net, findings[net.candidate_id], KNOWN_METRICS)
    assert verdict.state == "soft_rejected"
    assert verdict.failed_gate == "G5_deterministic_rules"


def test_pair_rule_respects_match_on_different_entities_not_compared():
    net = _fact(candidate_id="net1", entity_id="BH-1", metric_key="seam_thickness_net", value=Decimal("5"))
    gross = _fact(candidate_id="gross1", entity_id="BH-2", metric_key="seam_thickness_gross", value=Decimal("3"))
    findings = evaluate_pair_rules([net, gross], RULES)
    assert findings[net.candidate_id] == []


def test_warn_severity_does_not_block_only_flags():
    ash = _fact(candidate_id="ash1", entity_id="BH-1", metric_key="coal_ash_pct", value=Decimal("50"))
    gcv = _fact(candidate_id="gcv1", entity_id="BH-1", metric_key="coal_gcv", value=Decimal("6000"))
    findings = evaluate_pair_rules([ash, gcv], RULES)
    assert findings[ash.candidate_id][0].severity == "warn"
    verdict = run_gates(ash, findings[ash.candidate_id], KNOWN_METRICS)
    # warn doesn't soft-reject, but does prevent auto-pass (G7 routes to review)
    assert verdict.state == "pending_review"


def test_confidence_is_weakest_link_not_average():
    # perfect extraction, perfect entity, but a rulebook-default unit (weak)
    assert compose_confidence(1.0, "rulebook_default", True) == 0.6
    # perfect everything except entity resolution failed
    assert compose_confidence(1.0, "explicit_in_cell", False) == 0.5


def test_unresolved_header_chain_scores_low_even_with_perfect_text():
    from bhumi.read.confidence import compute_element_confidence

    ec = compute_element_confidence(tier=1, grid_consistency=1.0, header_resolved=False, cell_nonblank=True)
    assert ec.score < 0.5  # perfect text, but an unresolvable unit is unknowable, not "probably fine"
