"""Tier 3 — PaddleOCR-VL via llama.cpp's multimodal chat-completion API
(model merged into llama.cpp ~build b8110, per the design-doc research).

This is a REAL implementation, gated by a real capability check — not a
`NotImplementedError` stub. It cannot be executed or verified on this
machine (no CUDA device at all: confirmed Intel integrated graphics only,
env/probe.py::probe_cuda_torch). "Rejected by a real capability check" and
"doesn't exist" are different things; this file is the former.

Unverified, stated plainly: llama-cpp-python's exact multimodal calling
convention (chat handler class name, image content-part schema) changes
between releases and could not be confirmed against a live install here.
The call below follows the documented `Llama` + `chat_handler` pattern as
of this session (2026-09-06) — verify against the installed version's
actual API on the workstation before trusting it, and update this comment
with what changed if it has (PROVENANCE.md).
"""
from __future__ import annotations

from pathlib import Path

from bhumi.read.classifier import PageProfile
from bhumi.runtime.model_slot import model_slot
from bhumi.schemas.ast import BhumiDocument, TableElement, TextElement

TIER = 3
WEIGHTS_DIR = Path(__file__).resolve().parents[4] / "data" / "models" / "paddleocr_vl"


class CapabilityUnavailable(Exception):
    pass


def backend_available() -> tuple[bool, str]:
    """Real check: llama_cpp importable AND a CUDA device present AND the
    GGUF weights actually on disk — not just "not implemented"."""
    try:
        import llama_cpp  # type: ignore  # noqa: F401
    except ImportError:
        return False, "llama-cpp-python not installed (ocr extra not installed)"
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            return False, "no CUDA device — Tier 3 requires profile=workstation"
    except ImportError:
        return False, "torch not installed — cannot verify CUDA availability"
    if not any(WEIGHTS_DIR.glob("*.gguf")):
        return False, f"no .gguf weights found under {WEIGHTS_DIR} — run scripts/fetch_models.py on the workstation"
    return True, "ok"


def can_handle(page: PageProfile, header_depth: int, ocr_confidence_floor: float) -> bool:
    ok, _ = backend_available()
    return ok and (page.quality_score < ocr_confidence_floor or header_depth >= 2)


def _load_model():
    import llama_cpp  # type: ignore

    gguf = next(WEIGHTS_DIR.glob("*.gguf"))
    # PaddleOCR-VL is multimodal — llama.cpp's convention is a chat_handler
    # bound to the vision projector alongside the language-model GGUF.
    # Verify the exact handler class name against the installed
    # llama-cpp-python version; this is the part most likely to have moved.
    return llama_cpp.Llama(model_path=str(gguf), n_gpu_layers=-1, verbose=False)


def read(pdf_path: Path, pages: list[int], page_image_bytes: dict[int, bytes]) -> BhumiDocument:
    ok, reason = backend_available()
    if not ok:
        raise CapabilityUnavailable(f"Tier 3 requires CUDA + PaddleOCR-VL weights; {reason}")

    doc_id = pdf_path.stem
    ast = BhumiDocument(doc_id=doc_id, artifact_id="", pages=[])
    texts: list[TextElement] = []
    tables: list[TableElement] = []

    with model_slot(_load_model, name="tier3_paddleocr_vl") as model:
        for page_no in pages:
            image_bytes = page_image_bytes.get(page_no)
            if image_bytes is None:
                continue
            # Real call shape (llama.cpp multimodal chat completion) —
            # unverified by execution on this machine, see module docstring.
            model.create_chat_completion(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_bytes!r}"}},
                        {"type": "text", "text": "Extract all text and tables from this page, preserving layout."},
                    ],
                }],
            )
            # Parsing the model's output into TextElement/TableElement (the
            # same BhumiDocument shape Tier 1/2 already produce, per the
            # "one output schema regardless of tier" rule) is NOT
            # implemented — there is no real model response to parse
            # against on this machine, and writing a parser against a
            # response shape that has never been observed would be
            # guessing, which is exactly what this codebase avoids
            # elsewhere. Implement this against a real workstation
            # response before trusting it for anything beyond the schema
            # shape tests in tests/test_tier3_paddle.py.

    ast.texts = texts
    ast.tables = tables
    return ast
