"""`task assay reeval` — the demo moment (design doc M4.4): the system
improves retroactively over data it already rejected. Never touches
published/rejected rows; only re-runs gates on soft_rejected ones."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from bhumi.assay.gates import run_gates
from bhumi.assay.pipeline import load_known_metric_keys
from bhumi.assay.rule_engine import evaluate_pair_rules, evaluate_range_rules, load_rules
from bhumi.domain.entities import resolve_entity
from bhumi.domain.pack import DomainPack
from bhumi.schemas.core import CandidateFact, SourceRef
from bhumi.storage.db.models import CandidateFactRow

REPO_ROOT = Path(__file__).resolve().parents[3]


def _reresolve_entity(entity_raw: str, pack: DomainPack) -> str | None:
    """Try every entity pattern in the CURRENT pack against the raw text —
    a pack version bump (e.g. a widened borehole regex) is exactly what
    should let a previously-unresolvable entity resolve now."""
    if not entity_raw:
        return None
    for entity_type, pattern in pack.entity_patterns.items():
        resolved = resolve_entity(entity_type, entity_raw, pattern)
        if resolved:
            return resolved
    return None


def _row_to_fact(row: CandidateFactRow, pack: DomainPack) -> CandidateFact:
    entity_id = row.entity_id or _reresolve_entity(row.entity_raw, pack)
    return CandidateFact(
        candidate_id=row.candidate_id, entity_raw=row.entity_raw, entity_id=entity_id,
        metric_raw=row.metric_raw, metric_key=row.metric_key, value_raw=row.value_raw,
        value=row.value, unit=row.unit, unit_source=row.unit_source, qualifiers=row.qualifiers or {},
        value_kind=row.value_kind,
        period=row.period, status=row.status, source=SourceRef(**row.source),
        extraction_confidence=row.extraction_confidence, domain_type=row.domain_type,
        domain_pack_version=pack.version,
    )


def reeval_soft_rejected(session: Session, reason: str, pack: DomainPack, doc_id: str | None = None) -> dict:
    """Pair rules (e.g. net_le_gross) need BOTH sides of the comparison to
    be visible, and the passing side is usually NOT soft_rejected — so this
    loads every candidate for the doc to recompute findings correctly, but
    only ever writes a new state to rows that were actually soft_rejected.
    (Fixed 2026-09-05 after reeval silently "recovered" a candidate that
    should have stayed rejected — its paired sibling wasn't in scope.)"""
    all_query = select(CandidateFactRow)
    target_query = select(CandidateFactRow).where(CandidateFactRow.state == "soft_rejected")
    if doc_id:
        all_query = all_query.where(CandidateFactRow.doc_id == doc_id)
        target_query = target_query.where(CandidateFactRow.doc_id == doc_id)

    all_rows = list(session.execute(all_query).scalars().all())
    target_ids = {r.candidate_id for r in session.execute(target_query).scalars().all()}
    rows = [r for r in all_rows if r.candidate_id in target_ids]

    rules = load_rules(REPO_ROOT / "rulebook" / "rules" / "geology.yaml")
    known_metrics = load_known_metric_keys()
    all_facts = [_row_to_fact(r, pack) for r in all_rows]
    range_findings = evaluate_range_rules(all_facts, rules)
    pair_findings = evaluate_pair_rules(all_facts, rules)

    facts_by_id = {f.candidate_id: f for f in all_facts}
    recovered, unchanged = 0, 0
    for row in rows:
        fact = facts_by_id[row.candidate_id]
        findings = range_findings.get(fact.candidate_id, []) + pair_findings.get(fact.candidate_id, [])
        verdict = run_gates(fact, findings, known_metrics)
        if verdict.state != "soft_rejected":
            recovered += 1
        else:
            unchanged += 1
        row.state = verdict.state
        row.confidence = verdict.confidence
        row.gate_results = verdict.gate_results
        row.failed_gate = verdict.failed_gate
        row.failure_reason = verdict.failure_reason
        row.entity_id = fact.entity_id
        row.domain_pack_version = fact.domain_pack_version
        row.reeval_count += 1

    session.commit()
    return {"reason": reason, "total": len(rows), "recovered": recovered, "unchanged": unchanged}
