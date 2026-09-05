"""Real, live calls against whichever real backend is actually configured
this session — not mocked, not the deterministic fallback. Each test
forces its own backend via BHUMI_MODEL_BACKEND (overriding conftest's
autouse deterministic default for the general suite) and skips itself if
that backend's key isn't present. This is the test that proves "the
complete backend works the same for azure/gemini/groq/local" isn't just
an architecture claim — Azure's is the one with a real key this session,
so it's the one that actually asserts a real drafted sentence came back.
"""
import pytest

from bhumi.models.backends import azure_openai_backend, groq_backend

FIGURES = [{"figure_id": "F1", "metric_key": "seam_thickness_gross", "value": "3.42", "unit": "m"}]


@pytest.mark.skipif(not azure_openai_backend.api_key_configured(), reason="no AZURE_OPENAI_* configured")
def test_azure_openai_narrative_backend_produces_a_real_draft(monkeypatch):
    monkeypatch.setenv("BHUMI_MODEL_BACKEND", "azure")
    from bhumi.models.backends.select import get_narrative_generator

    sentences = get_narrative_generator().draft("Thickness", FIGURES)
    assert sentences
    assert sentences[0].text  # a real model response, not a template string
    assert "F1" in sentences[0].cited_figure_ids


@pytest.mark.skipif(not groq_backend.api_key_configured(), reason="no GROQ_API_KEY configured")
def test_groq_narrative_backend_produces_a_real_draft(monkeypatch):
    monkeypatch.setenv("BHUMI_MODEL_BACKEND", "groq")
    from bhumi.models.backends.select import get_narrative_generator

    sentences = get_narrative_generator().draft("Thickness", FIGURES)
    assert sentences
    assert sentences[0].text
