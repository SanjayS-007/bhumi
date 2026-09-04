"""What can this machine actually do? Honest about importable vs working.
See CLAUDE.md rule 3 — never claim untested capability.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CapabilityStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"


@dataclass
class Capability:
    name: str
    status: CapabilityStatus
    detail: str
    consequence: str
    verify_cmd: str | None = None
    remediation: str | None = None


def probe_python_runtime() -> Capability:
    v = sys.version_info
    ok = v.major == 3 and v.minor == 11
    return Capability(
        "python_runtime",
        CapabilityStatus.OK if ok else CapabilityStatus.DEGRADED,
        f"{sys.version.split()[0]} ({sys.executable}), 64-bit={sys.maxsize > 2**32}",
        "fine" if ok else "expected uv-managed 3.11; wheel availability for ML deps may differ",
    )


def probe_uv() -> Capability:
    uv = shutil.which("uv")
    if not uv:
        return Capability("uv", CapabilityStatus.UNAVAILABLE, "not on PATH",
                           "bootstrap.ps1 cannot run", remediation="irm https://astral.sh/uv/install.ps1 | iex")
    try:
        out = subprocess.run([uv, "--version"], capture_output=True, text=True, timeout=10)
        return Capability("uv", CapabilityStatus.OK, f"{uv} -> {out.stdout.strip()}", "task runner available")
    except Exception as e:
        return Capability("uv", CapabilityStatus.UNVERIFIED, f"found at {uv} but --version failed: {e}", "unknown")


def probe_admin_rights() -> Capability:
    import os
    target = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "bhumi_write_test.tmp"
    try:
        target.write_text("x")
        target.unlink()
        return Capability("admin_rights", CapabilityStatus.OK, "write to Program Files succeeded",
                           "elevated session — unusual for this project's target machine")
    except Exception as e:
        return Capability("admin_rights", CapabilityStatus.UNAVAILABLE, f"write denied: {e}",
                           "no MSI installers, no system services — expected and fine for profile=sqlite")


def probe_docker() -> Capability:
    docker = shutil.which("docker")
    if not docker:
        return Capability("docker", CapabilityStatus.UNAVAILABLE, "not installed",
                           "profile sqlite used instead of docker-compose Postgres")
    try:
        out = subprocess.run([docker, "version"], capture_output=True, text=True, timeout=10)
        ok = out.returncode == 0
        return Capability("docker", CapabilityStatus.OK if ok else CapabilityStatus.UNAVAILABLE,
                           out.stdout.strip()[:200], "workstation profile becomes possible" if ok else "daemon not reachable")
    except Exception as e:
        return Capability("docker", CapabilityStatus.UNAVAILABLE, str(e), "profile sqlite used instead")


def probe_long_paths() -> Capability:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            val, _ = winreg.QueryValueEx(k, "LongPathsEnabled")
        ok = val == 1
        return Capability("long_paths", CapabilityStatus.OK if ok else CapabilityStatus.DEGRADED,
                           f"LongPathsEnabled={val}", "fine" if ok else "keep repo path short; some ML package paths exceed 260 chars")
    except Exception as e:
        return Capability("long_paths", CapabilityStatus.DEGRADED, f"could not read registry: {e}",
                           "assume disabled; keep repo path short")


def probe_disk_space() -> Capability:
    total, used, free = shutil.disk_usage(Path.cwd().anchor)
    free_gb = free / 1e9
    status = CapabilityStatus.OK if free_gb >= 15 else CapabilityStatus.DEGRADED
    return Capability("disk_space", status, f"{free_gb:.1f} GB free on {Path.cwd().anchor}",
                       "fine" if free_gb >= 15 else "under 15GB free — ML model downloads may not fit")


def probe_ram() -> Capability:
    try:
        import psutil
        total_gb = psutil.virtual_memory().total / 1e9
        status = CapabilityStatus.OK if total_gb >= 8 else CapabilityStatus.DEGRADED
        return Capability("ram_total", status, f"{total_gb:.1f} GB total (workstation target 24 GB)",
                           "sqlite profile + Tier-1/Tier-2-CPU fits comfortably" if status == CapabilityStatus.OK
                           else "tight — avoid Docling CPU on large batches")
    except Exception as e:
        return Capability("ram_total", CapabilityStatus.UNVERIFIED, str(e), "unknown")


def probe_cpu() -> Capability:
    try:
        import psutil
        phys = psutil.cpu_count(logical=False)
        logical = psutil.cpu_count(logical=True)
        return Capability("cpu", CapabilityStatus.OK, f"{phys} physical / {logical} logical cores",
                           "affects Docling-CPU and llama.cpp throughput; no AVX2 check performed")
    except Exception as e:
        return Capability("cpu", CapabilityStatus.UNVERIFIED, str(e), "unknown")


def probe_cuda_torch() -> Capability:
    try:
        import torch  # type: ignore
    except ImportError:
        return Capability("cuda_torch", CapabilityStatus.UNAVAILABLE, "torch not installed (gpu extra not installed)",
                           "no GPU inference path buildable/testable here",
                           verify_cmd="BHUMI_PROFILE=workstation uv sync --extra gpu && python -c \"import torch;print(torch.cuda.is_available())\"")
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        return Capability("cuda_torch", CapabilityStatus.OK, f"CUDA available: {name}", "GPU tiers usable")
    return Capability("cuda_torch", CapabilityStatus.UNAVAILABLE, "torch installed, no CUDA device",
                       "confirmed no discrete GPU (Intel integrated graphics only) — Tier-3 OCR and GPU inference are UNAVAILABLE, not just untested")


def probe_sqlite_version() -> Capability:
    v = sqlite3.sqlite_version
    parts = tuple(int(x) for x in v.split("."))
    ok = parts >= (3, 38)
    return Capability("sqlite_version", CapabilityStatus.OK if ok else CapabilityStatus.DEGRADED,
                       f"sqlite3 {v}", "fine" if ok else "JSON support may be limited, upgrade Python")


def probe_sqlite_fts5() -> Capability:
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        con.execute("INSERT INTO t(body) VALUES ('hello world')")
        rows = con.execute("SELECT body FROM t WHERE t MATCH 'hello'").fetchall()
        con.close()
        ok = len(rows) == 1
        return Capability("sqlite_fts5", CapabilityStatus.OK if ok else CapabilityStatus.UNAVAILABLE,
                           f"virtual table created and queried, {len(rows)} row(s) matched", "text search usable (Phase 5)")
    except Exception as e:
        return Capability("sqlite_fts5", CapabilityStatus.UNAVAILABLE, str(e), "FTS5 not compiled into this sqlite3 build")


def probe_pymupdf() -> Capability:
    try:
        import fitz  # type: ignore
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "bhumi probe")
        text = page.get_text()
        doc.close()
        ok = "bhumi probe" in text
        return Capability("pymupdf", CapabilityStatus.OK if ok else CapabilityStatus.DEGRADED,
                           f"fitz {fitz.__doc__ or ''} — created and read back a 1-page PDF", "Tier-1 read path usable")
    except Exception as e:
        return Capability("pymupdf", CapabilityStatus.UNAVAILABLE, str(e),
                           "Tier-1 read path (the only tier this machine can run without extras) is broken")


def probe_docling() -> Capability:
    try:
        import docling  # type: ignore  # noqa: F401
    except ImportError:
        return Capability("docling", CapabilityStatus.UNAVAILABLE, "not installed (read extra not installed)",
                           "Tier-2 disabled; Tier-1 (PyMuPDF) still covers born-digital PDFs",
                           verify_cmd="uv sync --extra read")
    return Capability("docling", CapabilityStatus.UNVERIFIED, "importable, end-to-end convert not exercised by this probe",
                       "do not quote Docling accuracy/timing numbers from this result alone")


def probe_network(offline: bool) -> Capability:
    if offline:
        return Capability("network", CapabilityStatus.UNVERIFIED, "--offline requested, probe skipped", "n/a")
    import socket
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname("pypi.org")
        return Capability("network", CapabilityStatus.OK, "DNS resolution to pypi.org succeeded", "online features usable")
    except Exception as e:
        return Capability("network", CapabilityStatus.UNAVAILABLE, str(e), "acquire from URL will fail; use --offline")


def probe_huggingface_reachable(offline: bool) -> Capability:
    """huggingface.co is blocked at the network/proxy level on this
    machine — confirmed via raw HTTP request, HTTP 403 on the bare domain,
    not an app-level auth issue (verified 2026-09-06). This means
    embeddings/entailment models are CPU-viable in principle but their
    weights cannot actually be fetched here — a network policy, not a
    capability gap. scripts/fetch_models.py will correctly report
    'failed', not silently succeed."""
    if offline:
        return Capability("huggingface_reachable", CapabilityStatus.UNVERIFIED, "--offline requested, probe skipped", "n/a")
    try:
        import urllib.request

        req = urllib.request.Request("https://huggingface.co", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            code = resp.status
    except Exception as e:
        return Capability(
            "huggingface_reachable", CapabilityStatus.UNAVAILABLE, f"request failed: {e}",
            "model weight downloads (embeddings, entailment) will fail",
        )
    if code == 200:
        return Capability("huggingface_reachable", CapabilityStatus.OK, "HTTP 200", "model weight downloads should work")
    return Capability(
        "huggingface_reachable", CapabilityStatus.UNAVAILABLE, f"HTTP {code} on bare domain — network/proxy block, not an app error",
        "embeddings/entailment weights cannot be fetched on this network; try on the workstation or a different network",
    )


def probe_uv_project_environment() -> Capability:
    """A stray global UV_PROJECT_ENVIRONMENT pointing at an unrelated
    project silently redirects `uv venv`/`uv sync` — found and worked
    around 2026-09-04 (PROVENANCE.md). Encode the check, don't just
    document it."""
    val = os.environ.get("UV_PROJECT_ENVIRONMENT")
    repo_root = Path(__file__).resolve().parents[3]
    if not val:
        return Capability("uv_project_environment", CapabilityStatus.OK, "not set", "uv defaults to .venv inside the repo")
    try:
        inside_repo = repo_root in Path(val).resolve().parents or Path(val).resolve() == repo_root
    except OSError:
        inside_repo = False
    if inside_repo:
        return Capability("uv_project_environment", CapabilityStatus.OK, f"set to {val} (inside this repo)", "fine")
    return Capability(
        "uv_project_environment", CapabilityStatus.DEGRADED, f"set to {val} — NOT inside this repo ({repo_root})",
        "uv venv/uv sync will silently target the wrong project's virtualenv",
        remediation=f'unset UV_PROJECT_ENVIRONMENT (or set it to "{repo_root / ".venv"}") before running uv commands here',
    )


def probe_pytest_basetemp_writable() -> Capability:
    """pyproject.toml pins --basetemp=.pytest_tmp because this machine's
    default %TEMP%\\pytest-of-<user> was found unwritable (PROVENANCE.md).
    Verify that workaround is still valid rather than assuming it forever."""
    repo_root = Path(__file__).resolve().parents[3]
    basetemp = repo_root / ".pytest_tmp"
    try:
        basetemp.mkdir(parents=True, exist_ok=True)
        probe_file = basetemp / ".write_probe"
        probe_file.write_text("x")
        probe_file.unlink()
        return Capability("pytest_basetemp", CapabilityStatus.OK, f"{basetemp} is writable", "task test / task verify will run")
    except OSError as e:
        default_temp = Path(tempfile.gettempdir())
        return Capability(
            "pytest_basetemp", CapabilityStatus.UNAVAILABLE, f"{basetemp} not writable: {e}",
            "task test / task verify will fail with a confusing PermissionError",
            remediation=f"pick a writable --basetemp in pyproject.toml's [tool.pytest.ini_options] (default temp dir was {default_temp})",
        )


def run_all_probes(offline: bool = False) -> list[Capability]:
    return [
        probe_python_runtime(),
        probe_uv(),
        probe_uv_project_environment(),
        probe_admin_rights(),
        probe_docker(),
        probe_long_paths(),
        probe_disk_space(),
        probe_ram(),
        probe_cpu(),
        probe_cuda_torch(),
        probe_sqlite_version(),
        probe_sqlite_fts5(),
        probe_pytest_basetemp_writable(),
        probe_pymupdf(),
        probe_docling(),
        probe_network(offline),
        probe_huggingface_reachable(offline),
    ]
