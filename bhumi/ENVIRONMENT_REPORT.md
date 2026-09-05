# BHUMI Environment Report
Generated 2026-09-05T08:02:42+00:00 · profile `sqlite` · host LTIN708584 · platform Windows-10-10.0.26100-SP0

## Verdict
MVP-1 runnable via Tier-1 (PyMuPDF) read path on profile `sqlite`.
0 capabilities UNVERIFIED — require the workstation or extras not installed here.

## Summary
| Capability | Status | Detail |
|---|---|---|
| python_runtime | ok | 3.11.15 (C:\Users\2504690\2026\bhumi\.venv\Scripts\python.exe), 64-bit=True |
| uv | ok | C:\Users\2504690\AppData\Roaming\Python\Python313\Scripts\uv.EXE -> uv 0.11.8 (0e961dd9a 2026-04-27 x86_64-pc-windows-msvc) |
| uv_project_environment | degraded | set to C:\dev\src\cne-platform-venv — NOT inside this repo (C:\Users\2504690\2026\bhumi) |
| admin_rights | unavailable | write denied: [Errno 13] Permission denied: 'C:\\Program Files\\bhumi_write_test.tmp' |
| docker | unavailable | not installed |
| long_paths | degraded | LongPathsEnabled=0 |
| disk_space | ok | 286.5 GB free on C:\ |
| ram_total | ok | 16.6 GB total (workstation target 24 GB) |
| cpu | ok | 10 physical / 12 logical cores |
| cuda_torch | unavailable | torch not installed (gpu extra not installed) |
| sqlite_version | ok | sqlite3 3.50.4 |
| sqlite_fts5 | ok | virtual table created and queried, 1 row(s) matched |
| pytest_basetemp | ok | C:\Users\2504690\2026\bhumi\.pytest_tmp is writable |
| pymupdf | ok | fitz PyMuPDF 1.28.2: Python bindings for the MuPDF 1.28.2 library.
Python 3.11 running on win32 (64-bit).
 — created and read back a 1-page PDF |
| docling | unavailable | not installed (read extra not installed) |
| network | ok | DNS resolution to pypi.org succeeded |
| huggingface_reachable | unavailable | request failed: HTTP Error 403: Forbidden |

## Cannot be verified on this machine
### cuda_torch
- **Consequence:** no GPU inference path buildable/testable here
- **Verify:** `BHUMI_PROFILE=workstation uv sync --extra gpu && python -c "import torch;print(torch.cuda.is_available())"`

### docling
- **Consequence:** Tier-2 disabled; Tier-1 (PyMuPDF) still covers born-digital PDFs
- **Verify:** `uv sync --extra read`


## Model availability
| Model | Installable here | Runnable here | Weights fetched | Verified by |
|---|---|---|---|---|
| bge-small-en-v1.5 (embeddings) | yes | yes (CPU) | **no — huggingface.co blocked at network/proxy level (HTTP 403 on bare domain, confirmed 2026-09-06)** | not run — network blocked; code path real, see scripts/fetch_models.py |
| MiniCheck-Flan-T5-Large (entailment) | yes | yes (CPU) | **deliberately not fetched — explicit instruction this session, not a capability gap** | n/a |
| Docling layout+TableFormer (CPU) | yes | not run this session | n/a | Tier 1 (PyMuPDF) covered the real document end to end; Docling was never invoked |
| Docling (GPU) | yes | no — no CUDA | n/a | skipped, requires workstation |
| PaddleOCR-VL (Tier 3) | yes (real code written, gated) | no — no CUDA | no — skipped by profile | code path exists and is capability-gated; run `pytest -m requires_gpu` on the workstation |
| Local narrative LLM (Qwen2.5-3B) | yes (CPU wheel path) | not run | no — workstation profile only | not attempted this session |

## Recommended profile for this machine
`sqlite` — matches measured capabilities above.
