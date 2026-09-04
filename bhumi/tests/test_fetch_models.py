"""fetch_models.py, with the network layer mocked — assert profile/CUDA
gating and BHUMI_SKIP_MODELS work, and that a fully-populated data/models/
directory makes zero download calls."""

from scripts.fetch_models import ModelSpec, fetch_all


def _spec(name, profile_required="any", requires_cuda=False, target_dir=None) -> ModelSpec:
    return ModelSpec(
        name=name, profile_required=profile_required, requires_cuda=requires_cuda,
        source=f"org/{name}", target_dir=target_dir, expected_files=["config.json"],
    )


def test_gpu_only_model_skipped_without_cuda(tmp_path):
    specs = [_spec("gpu_model", requires_cuda=True, target_dir=tmp_path / "gpu_model")]
    calls = []
    results = fetch_all("sqlite", specs, cuda_available=lambda: False, downloader=lambda s: calls.append(s) or (0, 0))
    assert results[0].status == "skipped"
    assert "no CUDA" in results[0].detail
    assert calls == []


def test_workstation_only_model_skipped_on_sqlite_profile(tmp_path):
    specs = [_spec("ws_model", profile_required="workstation", target_dir=tmp_path / "ws_model")]
    results = fetch_all("sqlite", specs, cuda_available=lambda: False, downloader=lambda s: (0, 0))
    assert results[0].status == "skipped"
    assert "requires workstation" in results[0].detail


def test_explicit_skip_env_var_overrides_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("BHUMI_SKIP_MODELS", "entailment_minicheck,other")
    specs = [_spec("entailment_minicheck", target_dir=tmp_path / "e")]
    calls = []
    results = fetch_all("sqlite", specs, cuda_available=lambda: True, downloader=lambda s: calls.append(s) or (0, 0))
    assert results[0].status == "skipped"
    assert calls == []


def test_already_present_model_makes_no_download_call(tmp_path):
    target = tmp_path / "present_model"
    target.mkdir()
    (target / "config.json").write_text("{}")
    specs = [_spec("present_model", target_dir=target)]
    calls = []
    results = fetch_all("sqlite", specs, cuda_available=lambda: True, downloader=lambda s: calls.append(s) or (0, 0))
    assert results[0].status == "already_present"
    assert calls == []


def test_missing_model_actually_calls_downloader(tmp_path):
    specs = [_spec("new_model", target_dir=tmp_path / "new_model")]
    calls = []
    results = fetch_all("sqlite", specs, cuda_available=lambda: True, downloader=lambda s: (calls.append(s.name), (12.3, 4.5))[1])
    assert results[0].status == "downloaded"
    assert calls == ["new_model"]
    assert results[0].mb == 12.3
