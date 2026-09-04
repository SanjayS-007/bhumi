# PROVENANCE — decision log

Every non-obvious choice, with a date and a reason. Append, never rewrite history.

- **2026-09-04** — Default profile is `sqlite`, not `supabase` or `workstation`. Reason: build laptop has no admin rights, no Docker, no local Postgres, and no CUDA GPU (verified: Intel integrated graphics only, 15.5GB RAM, non-admin). `sqlite` must run the full MVP-1 demo offline.
- **2026-09-04** — Python 3.11 via `uv`-managed interpreter, not the system Python 3.13 (`C:\Program Files\Python313`). Reason: ML wheel availability (Docling, PaddleOCR stack) lags on 3.12/3.13; uv installs its own interpreter so the system Python version doesn't matter.
- **2026-09-04** — `uv` was already present on this machine at `AppData\Roaming\Python\Python313\Scripts\uv`, not the standard `%USERPROFILE%\.local\bin`. bootstrap.ps1 does not assume a fixed uv location; it just checks PATH.
- **2026-09-04** — Tier 3 OCR (PaddleOCR-VL GPU) is `UNAVAILABLE` on this machine, not `UNVERIFIED` — no CUDA device present (Intel Graphics only). `ENVIRONMENT_REPORT.md` must say this plainly once `task doctor` exists.
