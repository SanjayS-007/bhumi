"""Phase 4 orchestrator: type a document (Phase 3), run every candidate
through the seven gates, persist the state machine."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import structlog
import yaml
from sqlalchemy.orm import Session

from bhumi.assay.gates import run_gates
from bhumi.assay.rule_engine import evaluate_pair_rules, evaluate_range_rules, load_rules
from bhumi.domain.pack import DomainPack
from bhumi.domain.pipeline import type_document
from bhumi.storage.db.models import AssayRun, CandidateFactRow

log = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_known_metric_keys() -> set[str]:
    data = yaml.safe_load((REPO_ROOT / "rulebook" / "metrics.yaml").read_text(encoding="utf-8"))
    return set(data["metrics"].keys())


def run_assay(session: Session, doc_id: str, artifact_id: str, ast_path: str, pack: DomainPack) -> dict:
    ast = json.loads(Path(ast_path).read_text(encoding="utf-8"))
    candidates = type_document(ast, doc_id, artifact_id, pack)

    rules = load_rules(REPO_ROOT / "rulebook" / "rules" / "geology.yaml")
    range_findings = evaluate_range_rules(candidates, rules)
    pair_findings = evaluate_pair_rules(candidates, rules)
    known_metrics = load_known_metric_keys()

    run_id = str(uuid.uuid4())
    state_counts: dict[str, int] = {}
    gate_failure_counts: dict[str, int] = {}

    for c in candidates:
        findings = range_findings.get(c.candidate_id, []) + pair_findings.get(c.candidate_id, [])
        verdict = run_gates(c, findings, known_metrics)

        state_counts[verdict.state] = state_counts.get(verdict.state, 0) + 1
        if verdict.failed_gate:
            gate_failure_counts[verdict.failed_gate] = gate_failure_counts.get(verdict.failed_gate, 0) + 1

        row = session.get(CandidateFactRow, c.candidate_id)
        if row is None:
            row = CandidateFactRow(candidate_id=c.candidate_id)
            session.add(row)
        row.doc_id = doc_id
        row.entity_raw = c.entity_raw
        row.entity_id = c.entity_id
        row.metric_raw = c.metric_raw
        row.metric_key = c.metric_key
        row.value_raw = c.value_raw
        row.value = c.value
        row.unit = c.unit
        row.unit_source = c.unit_source
        row.qualifiers = c.qualifiers
        row.period = c.period
        row.status = c.status
        row.source = c.source.model_dump()
        row.extraction_confidence = c.extraction_confidence
        row.domain_type = c.domain_type
        row.domain_pack_version = c.domain_pack_version
        row.state = verdict.state
        row.confidence = verdict.confidence
        row.gate_results = verdict.gate_results
        row.failed_gate = verdict.failed_gate
        row.failure_reason = verdict.failure_reason
        row.assay_run_id = run_id

    session.add(
        AssayRun(
            run_id=run_id, doc_id=doc_id, domain_pack_version=pack.version,
            state_counts=state_counts, gate_failure_counts=gate_failure_counts,
        )
    )
    session.commit()
    log.info("assay_run_done", doc_id=doc_id, run_id=run_id, candidates=len(candidates), state_counts=state_counts)
    return {"run_id": run_id, "candidates": len(candidates), "state_counts": state_counts, "gate_failure_counts": gate_failure_counts}
