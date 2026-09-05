"""Proves the calling code (agents, narrative drafting) is backend-
agnostic: swap the backend implementation in the fixture, assert the
calling function's behavior/contract is unchanged — it only depends on
the Protocol, never on which class implements it."""
from bhumi.models.backends.deterministic_backend import (
    DeterministicEntailmentBackend,
    DeterministicNarrativeBackend,
)
from bhumi.models.backends.select import api_key_configured, get_entailment_checker, get_narrative_generator


def draft_and_gate(narrative_backend, entailment_backend, section_title, figures):
    """Stand-in for the Narrative Track + Proof Gate — takes Protocol
    instances, never a concrete class."""
    evidence = [{"raw_text": f"{f['metric_key']} {f['value']} {f.get('unit', '')}"} for f in figures]
    sentences = narrative_backend.draft(section_title, figures)
    verdicts = [entailment_backend.check(s.text, evidence) for s in sentences]
    return sentences, verdicts


def test_calling_code_works_identically_with_either_backend_selected_by_config():
    figures = [{"figure_id": "F1", "metric_key": "seam_thickness_gross", "value": "3.42", "unit": "m"}]

    # Backend A: deterministic, explicit
    sentences_a, verdicts_a = draft_and_gate(
        DeterministicNarrativeBackend(), DeterministicEntailmentBackend(), "Thickness", figures
    )
    assert sentences_a[0].cited_figure_ids == ["F1"]
    assert verdicts_a[0].entailed  # "3.42" appears verbatim in the drafted sentence

    # Backend B: whatever select.py currently resolves to given
    # BHUMI_MODEL_BACKEND/env (conftest forces deterministic for the
    # general suite) — the calling function above required zero changes
    # to accept either.
    narrative = get_narrative_generator()
    entailment = get_entailment_checker()
    sentences_b, verdicts_b = draft_and_gate(narrative, entailment, "Thickness", figures)
    assert sentences_b[0].cited_figure_ids  # some figure was cited, regardless of backend
    assert isinstance(verdicts_b[0].entailed, bool)


def test_select_returns_deterministic_when_no_key_configured(monkeypatch):
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION"):
        monkeypatch.delenv(var, raising=False)
    assert not api_key_configured()
    from bhumi.models.backends.deterministic_backend import DeterministicRerankerBackend

    from bhumi.models.backends.select import get_reranker
    assert isinstance(get_reranker(), DeterministicRerankerBackend)


def test_forced_deterministic_backend_via_env(monkeypatch):
    monkeypatch.setenv("BHUMI_MODEL_BACKEND", "deterministic")
    from bhumi.models.backends.deterministic_backend import DeterministicRerankerBackend

    from bhumi.models.backends.select import get_reranker
    assert isinstance(get_reranker(), DeterministicRerankerBackend)
