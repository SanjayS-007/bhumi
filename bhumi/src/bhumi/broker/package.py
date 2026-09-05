"""Immutable, content-addressed EvidencePackage — the sealed artifact both
agents actually consume. Minimal shape: intent, the principal snapshot
(so the cache/audit key includes policy, per the design doc's explicit
warning about leaking restricted evidence through an unkeyed cache),
facts, passages, coverage, and a deterministic hash.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass
class EvidencePackage:
    intent: str
    principal_subject: str
    max_classification: list[str]
    facts: list[dict] = field(default_factory=list)
    passages: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    package_id: str = ""
    content_hash: str = ""

    def seal(self) -> "EvidencePackage":
        canonical = json.dumps(
            {
                "intent": self.intent, "principal_subject": self.principal_subject,
                "max_classification": sorted(self.max_classification),
                "facts": self.facts, "passages": self.passages, "coverage": self.coverage,
            },
            sort_keys=True, default=str,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        self.content_hash = digest
        self.package_id = f"SEP-{digest[:12]}"
        return self

    def to_dict(self) -> dict:
        return asdict(self)
