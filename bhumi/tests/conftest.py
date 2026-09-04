"""`@pytest.mark.requires_gpu` tests are auto-skipped when no CUDA device
is present — checked for real (not just "skip everything on this OS"),
matching CLAUDE.md rule 3: never claim untested capability, and never
silently skip a test that could actually run."""
import pytest


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def pytest_collection_modifyitems(config, items):
    if _cuda_available():
        return
    skip_gpu = pytest.mark.skip(reason="no CUDA device on this machine — run on the workstation")
    for item in items:
        if "requires_gpu" in item.keywords:
            item.add_marker(skip_gpu)
