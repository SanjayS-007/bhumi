"""`@pytest.mark.requires_gpu` tests are auto-skipped when no CUDA device
is present — checked for real (not just "skip everything on this OS"),
matching CLAUDE.md rule 3: never claim untested capability, and never
silently skip a test that could actually run."""
import pytest


@pytest.fixture(autouse=True)
def _default_to_deterministic_backend(monkeypatch):
    """Real API keys live in `.env` for manual/live verification (see
    tests/test_live_backends.py), but the general suite must stay fast,
    free, and offline per CLAUDE.md rule 7 — force the deterministic
    backend unless a test explicitly overrides BHUMI_MODEL_BACKEND
    itself (monkeypatch inside a test wins over this outer one)."""
    monkeypatch.setenv("BHUMI_MODEL_BACKEND", "deterministic")


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
