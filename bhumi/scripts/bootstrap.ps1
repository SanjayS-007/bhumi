# BHUMI bootstrap — must work in a non-elevated PowerShell session.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1

$ErrorActionPreference = "Stop"
function Ok($msg)   { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

Write-Host "PowerShell $($PSVersionTable.PSVersion)"
if ($PSVersionTable.PSVersion.Major -lt 5) { Warn "PowerShell < 5.1 — untested" } else { Ok "PowerShell version fine" }

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Warn "uv not found on PATH — installing to user scope"
    irm https://astral.sh/uv/install.ps1 | iex
} else {
    Ok "uv found: $($uv.Source)"
}

uv python install 3.11
Ok "uv-managed Python 3.11 available"

if (-not (Test-Path ".venv")) {
    uv venv --python 3.11
    Ok "venv created"
} else {
    Ok "venv already exists"
}

uv sync --frozen
Ok "dependencies synced from lockfile"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Ok ".env created from .env.example"
} else {
    Ok ".env already exists"
}

foreach ($d in @("data/vault","data/ast","data/rasters","data/models")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
Ok "data/ tree present"

try {
    $lp = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    if ($lp -eq 1) { Ok "Long paths enabled" } else { Warn "Long paths NOT enabled — keep repo path short" }
} catch {
    Warn "Could not read LongPathsEnabled — assume disabled, keep repo path short"
}

Write-Host ""
Write-Host "Next: uv run task doctor" -ForegroundColor Cyan
