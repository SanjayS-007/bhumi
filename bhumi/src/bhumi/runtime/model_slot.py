"""Load a model, yield it, free it. Every model load in the codebase goes
through this — see CLAUDE.md rule 11. No GPU on this machine to protect yet,
but Tier-2/3 on the workstation must use the identical code path.
"""
from __future__ import annotations

import gc
from contextlib import contextmanager

import structlog

log = structlog.get_logger()


@contextmanager
def model_slot(loader, name: str):
    m = loader()
    try:
        yield m
    finally:
        del m
        gc.collect()
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                free, _ = torch.cuda.mem_get_info()
                log.info("model_unloaded", model=name, vram_free_gb=round(free / 1e9, 2))
                return
        except ImportError:
            pass
        log.info("model_unloaded", model=name, vram_free_gb=None)
