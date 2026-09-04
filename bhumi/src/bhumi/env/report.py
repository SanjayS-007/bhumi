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

    lines += [
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
