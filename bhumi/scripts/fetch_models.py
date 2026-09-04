"""Idempotent, profile-aware model fetcher (addon prompt §2). Skips
anything already present, anything the active profile doesn't need, and
anything requiring CUDA on a machine without it. Never requires admin
rights — everything lands under data/models/.

Explicit per-model skip: BHUMI_SKIP_MODELS="entailment_minicheck,foo" lets
a specific model be excluded even when the profile/CUDA gate would allow
it — used this session to keep a genuinely CPU-viable 3GB+ model off this
laptop by instruction, not by capability limitation. See PROVENANCE.md
2026-09-06.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class ModelSpec:
    name: str
    profile_required: str
    requires_cuda: bool
    source: str
    target_dir: Path
    expected_files: list[str]


@dataclass
class FetchResult:
    name: str
    status: str  # already_present | downloaded | skipped | failed
    detail: str
    mb: float = 0.0
    seconds: float = 0.0


def load_model_specs(path: Path | None = None) -> list[ModelSpec]:
    path = path or (REPO_ROOT / "config" / "models.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    specs = []
    for name, m in data["models"].items():
        specs.append(ModelSpec(
            name=name, profile_required=m["profile_required"], requires_cuda=m["requires_cuda"],
            source=m["source"], target_dir=REPO_ROOT / m["target_dir"], expected_files=m["expected_files"],
        ))
    return specs


def _already_present(spec: ModelSpec) -> bool:
    if not spec.target_dir.exists():
        return False
    if not spec.expected_files:
        return any(spec.target_dir.iterdir())
    for pattern in spec.expected_files:
        if not list(spec.target_dir.glob(pattern)):
            return False
    return True


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def _download_hf(spec: ModelSpec) -> tuple[float, float]:
    from huggingface_hub import snapshot_download

    started = time.monotonic()
    spec.target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=spec.source, local_dir=str(spec.target_dir))
    elapsed = time.monotonic() - started
    total_bytes = sum(f.stat().st_size for f in spec.target_dir.rglob("*") if f.is_file())
    return total_bytes / 1e6, elapsed


def fetch_all(
    profile: str,
    specs: list[ModelSpec] | None = None,
    cuda_available: Callable[[], bool] = _cuda_available,
    downloader: Callable[[ModelSpec], tuple[float, float]] = _download_hf,
) -> list[FetchResult]:
    specs = specs if specs is not None else load_model_specs()
    skip_names = {s.strip() for s in os.environ.get("BHUMI_SKIP_MODELS", "").split(",") if s.strip()}
    results: list[FetchResult] = []

    for spec in specs:
        if spec.name in skip_names:
            results.append(FetchResult(spec.name, "skipped", f"BHUMI_SKIP_MODELS explicitly excludes {spec.name}"))
            continue
        if spec.profile_required != "any" and spec.profile_required != profile:
            results.append(FetchResult(spec.name, "skipped", f"profile={profile} does not need this (requires {spec.profile_required})"))
            continue
        if spec.requires_cuda and not cuda_available():
            results.append(FetchResult(spec.name, "skipped", f"skipping {spec.name}: profile={profile} has no CUDA device (workstation profile required)"))
            continue
        if _already_present(spec):
            results.append(FetchResult(spec.name, "already_present", str(spec.target_dir)))
            continue
        try:
            mb, seconds = downloader(spec)
            results.append(FetchResult(spec.name, "downloaded", spec.source, mb=round(mb, 1), seconds=round(seconds, 1)))
        except Exception as e:  # network/HF errors are expected offline — never crash the caller
            results.append(FetchResult(spec.name, "failed", str(e)))
    return results


def total_disk_mb(root: Path = REPO_ROOT / "data" / "models") -> float:
    if not root.exists():
        return 0.0
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) / 1e6


if __name__ == "__main__":
    from bhumi.config.settings import get_settings

    settings = get_settings()
    results = fetch_all(settings.profile.value)
    for r in results:
        extra = f" ({r.mb} MB, {r.seconds}s)" if r.status == "downloaded" else ""
        print(f"[{r.status}] {r.name}: {r.detail}{extra}")
    print(f"total disk used under data/models/: {total_disk_mb():.1f} MB")
