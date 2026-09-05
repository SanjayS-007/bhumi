"""The Gemini key configured this session is malformed (Google's own
server: `ACCESS_TOKEN_TYPE_UNSUPPORTED` — see PROVENANCE.md 2026-09-06).
This test proves the fallback wrapper survives that failure mode without
crashing the caller, using the REAL Gemini backend (not mocked) so it's an
honest test of the actual bad-key behavior, not a simulation of it. Forces
BHUMI_MODEL_BACKEND=gemini so it exercises Gemini specifically, overriding
conftest's autouse deterministic default for the general suite."""
import pytest

from bhumi.models.backends import gemini_backend


@pytest.mark.skipif(not gemini_backend.api_key_configured(), reason="no GEMINI_API_KEY configured in this environment")
def test_narrative_falls_back_when_gemini_call_fails(monkeypatch):
    monkeypatch.setenv("BHUMI_MODEL_BACKEND", "gemini")
    from bhumi.models.backends.select import get_narrative_generator

    generator = get_narrative_generator()
    figures = [{"figure_id": "F1", "metric_key": "seam_thickness_gross", "value": "3.42", "unit": "m"}]
    # Must not raise, even though the underlying Gemini call is expected
    # to fail (bad key) — the wrapper catches it and falls back.
    sentences = generator.draft("Thickness", figures)
    assert sentences
    assert sentences[0].cited_figure_ids
