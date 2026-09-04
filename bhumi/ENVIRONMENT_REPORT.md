# BHUMI Environment Report
Generated 2026-09-04T11:05:30+00:00 · profile `sqlite` · host LTIN708584 · platform Windows-10-10.0.26100-SP0

## Verdict
MVP-1 runnable via Tier-1 (PyMuPDF) read path on profile `sqlite`.
0 capabilities UNVERIFIED — require the workstation or extras not installed here.

## Summary
| Capability | Status | Detail |
|---|---|---|
| python_runtime | ok | 3.11.15 (C:\Users\2504690\2026\bhumi\.venv\Scripts\python.exe), 64-bit=True |
| uv | ok | C:\Users\2504690\AppData\Roaming\Python\Python313\Scripts\uv.EXE -> uv 0.11.8 (0e961dd9a 2026-04-27 x86_64-pc-windows-msvc) |
| admin_rights | unavailable | write denied: [Errno 13] Permission denied: 'C:\\Program Files\\bhumi_write_test.tmp' |
| docker | unavailable | not installed |
| long_paths | degraded | LongPathsEnabled=0 |
| disk_space | ok | 282.8 GB free on C:\ |
| ram_total | ok | 16.6 GB total (workstation target 24 GB) |
| cpu | ok | 10 physical / 12 logical cores |
| cuda_torch | unavailable | torch not installed (gpu extra not installed) |
| sqlite_version | ok | sqlite3 3.50.4 |
| sqlite_fts5 | ok | virtual table created and queried, 1 row(s) matched |
| pymupdf | ok | fitz PyMuPDF 1.28.2: Python bindings for the MuPDF 1.28.2 library.
Python 3.11 running on win32 (64-bit).
 — created and read back a 1-page PDF |
| docling | unavailable | not installed (read extra not installed) |
| network | ok | DNS resolution to pypi.org succeeded |

## Cannot be verified on this machine
### cuda_torch
- **Consequence:** no GPU inference path buildable/testable here
- **Verify:** `BHUMI_PROFILE=workstation uv sync --extra gpu && python -c "import torch;print(torch.cuda.is_available())"`

### docling
- **Consequence:** Tier-2 disabled; Tier-1 (PyMuPDF) still covers born-digital PDFs
- **Verify:** `uv sync --extra read`

## Recommended profile for this machine
`sqlite` — matches measured capabilities above.
