"""Resource-budget admission check (base design §7) — before `serve`'s
self-healing sequence hands off to the UI, check whether the models it
just fetched/verified would fit this profile's RAM/VRAM budget, and say
so plainly. Estimates, not measurements: `config/resources.yaml`'s
per-model costs are documented approximations, not values measured by an
actual load on this machine (no GPU here, and most of these models were
never fetched here at all — see PROVENANCE.md). This check is advisory
today, not a hard gate, because no model in this codebase auto-loads at
serve-time yet on the sqlite profile — there's nothing for it to actually
block. It exists and is exercised (see tests/test_resources.py) so it's
real and ready the moment that changes, not decoration.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCES_PATH = REPO_ROOT / "config" / "resources.yaml"


@dataclass
class AdmissionResult:
    admitted: bool
    reason: str
    estimated_ram_gb: float
    available_ram_gb: float
    estimated_vram_gb: float
    available_vram_gb: float


def _load_resources(path: Path = RESOURCES_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _available_ram_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 1e9


def _available_vram_gb() -> float:
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            return free / 1e9
    except ImportError:
        pass
    return 0.0


def check_admission(
    profile: str, planned_models: list[str], *,
    max_ram_gb: float | None = None, max_vram_gb: float | None = None,
    resources_path: Path = RESOURCES_PATH,
    available_ram_gb: float | None = None, available_vram_gb: float | None = None,
) -> AdmissionResult:
    """`max_ram_gb`/`max_vram_gb` are the explicit `Settings` override
    (CLAUDE.md's existing `max_ram_gb`/`max_vram_gb` fields) — they win
    over the profile's default budget when set. `available_*_gb` are
    injectable for tests; default to real `psutil`/`torch` readings."""
    resources = _load_resources(resources_path)
    budget = resources["budgets"].get(profile, {})
    costs = resources["model_costs_gb"]

    est_ram = sum(costs.get(m, {}).get("ram", 0.0) for m in planned_models)
    est_vram = sum(costs.get(m, {}).get("vram", 0.0) for m in planned_models)

    avail_ram = available_ram_gb if available_ram_gb is not None else _available_ram_gb()
    avail_vram = available_vram_gb if available_vram_gb is not None else _available_vram_gb()

    budget_ram = max_ram_gb or budget.get("max_ram_gb") or avail_ram
    budget_vram = max_vram_gb if max_vram_gb is not None else budget.get("max_vram_gb", 0.0)

    # a profile with zero VRAM budget has no CUDA path at all — every
    # model estimate's VRAM component is "cost IF it used the GPU," which
    # never happens here, so it would never actually be spent; only a
    # profile that *has* a CUDA budget can meaningfully exceed it
    if budget_vram <= 0.0:
        est_vram = 0.0

    if est_vram > budget_vram:
        return AdmissionResult(False, f"estimated VRAM {est_vram:.1f}GB exceeds this profile's budget of {budget_vram:.1f}GB", est_ram, avail_ram, est_vram, avail_vram)
    if est_ram > budget_ram:
        return AdmissionResult(False, f"estimated RAM {est_ram:.1f}GB exceeds the configured budget of {budget_ram:.1f}GB", est_ram, avail_ram, est_vram, avail_vram)
    if est_ram > avail_ram:
        return AdmissionResult(False, f"estimated RAM {est_ram:.1f}GB exceeds what's currently available ({avail_ram:.1f}GB)", est_ram, avail_ram, est_vram, avail_vram)
    if est_vram > avail_vram:
        return AdmissionResult(False, f"estimated VRAM {est_vram:.1f}GB exceeds what's currently available ({avail_vram:.1f}GB)", est_ram, avail_ram, est_vram, avail_vram)
    return AdmissionResult(True, "within budget", est_ram, avail_ram, est_vram, avail_vram)
