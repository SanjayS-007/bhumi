from __future__ import annotations

from pathlib import Path

import yaml

from bhumi.domain.pack import DomainPack


def load_pack(path: Path) -> DomainPack:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DomainPack(**data)


def load_default_pack() -> DomainPack:
    """domain/packs/geological_report.yaml, resolved relative to the repo root."""
    root = Path(__file__).resolve().parents[3]  # src/bhumi/domain/ -> repo root
    return load_pack(root / "domain" / "packs" / "geological_report.yaml")
