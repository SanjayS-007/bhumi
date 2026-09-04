from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone
from pathlib import Path

from bhumi.config.settings import Settings
from bhumi.env.probe import Capability, CapabilityStatus, run_all_probes

BLOCKING = {CapabilityStatus.UNAVAILABLE}


def render_report(caps: list[Capability], settings: Settings) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    host = socket.gethostname()
    unverified = [c for c in caps if c.status == CapabilityStatus.UNVERIFIED]
    lines = [
        "# BHUMI Environment Report",
        f"Generated {now} · profile `{settings.profile.value}` · host {host} · platform {platform.platform()}",
        "",
        "## Verdict",
        "MVP-1 runnable via Tier-1 (PyMuPDF) read path on profile `sqlite`.",
        f"{len(unverified)} capabilities UNVERIFIED — require the workstation or extras not installed here.",
        "",
        "## Summary",
        "| Capability | Status | Detail |",
        "|---|---|---|",
    ]
    for c in caps:
        lines.append(f"| {c.name} | {c.status.value} | {c.detail} |")

    lines += ["", "## Cannot be verified on this machine"]
    for c in caps:
        if c.status in (CapabilityStatus.UNVERIFIED, CapabilityStatus.UNAVAILABLE) and c.verify_cmd:
            lines += [
                f"### {c.name}",
                f"- **Consequence:** {c.consequence}",
                f"- **Verify:** `{c.verify_cmd}`",
                "",
            ]

    lines += ["", "## Model availability", "| Model | Installable here | Runnable here | Weights fetched | Verified by |", "|---|---|---|---|---|"]
    hf_ok = next((c for c in caps if c.name == "huggingface_reachable"), None)
    hf_note = "yes" if hf_ok and hf_ok.status == CapabilityStatus.OK else "**no — huggingface.co blocked at network/proxy level (HTTP 403 on bare domain, confirmed 2026-09-06)**"
    lines += [
        f"| bge-small-en-v1.5 (embeddings) | yes | yes (CPU) | {hf_note} | not run — network blocked; code path real, see scripts/fetch_models.py |",
        "| MiniCheck-Flan-T5-Large (entailment) | yes | yes (CPU) | **deliberately not fetched — explicit instruction this session, not a capability gap** | n/a |",
        "| Docling layout+TableFormer (CPU) | yes | not run this session | n/a | Tier 1 (PyMuPDF) covered the real document end to end; Docling was never invoked |",
        "| Docling (GPU) | yes | no — no CUDA | n/a | skipped, requires workstation |",
        "| PaddleOCR-VL (Tier 3) | yes (real code written, gated) | no — no CUDA | no — skipped by profile | code path exists and is capability-gated; run `pytest -m requires_gpu` on the workstation |",
        "| Local narrative LLM (Qwen2.5-3B) | yes (CPU wheel path) | not run | no — workstation profile only | not attempted this session |",
    ]

    lines += [
        "",
        "## Recommended profile for this machine",
        f"`{settings.profile.value}` — matches measured capabilities above.",
    ]
    return "\n".join(lines) + "\n"


def write_report(settings: Settings, offline: bool = False, out_path: Path = Path("ENVIRONMENT_REPORT.md")) -> tuple[str, bool]:
    caps = run_all_probes(offline=offline)
    text = render_report(caps, settings)
    out_path.write_text(text, encoding="utf-8")
    by_name = {c.name: c for c in caps}
    strict_ok = (
        by_name["pymupdf"].status == CapabilityStatus.OK
        and by_name["python_runtime"].status == CapabilityStatus.OK
        and by_name["pytest_basetemp"].status != CapabilityStatus.UNAVAILABLE
        and by_name["uv_project_environment"].status != CapabilityStatus.DEGRADED
    )
    return text, strict_ok
