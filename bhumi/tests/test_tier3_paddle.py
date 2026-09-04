"""Tier 3's capability gate — the part that CAN be verified without a GPU.
The actual inference path is @requires_gpu and skipped here (see
conftest.py); backend_available() correctly returning False, with a real
reason, is the thing this machine can and must prove."""
import pytest

from bhumi.read.tiers import tier3_paddle


def test_backend_unavailable_without_cuda_reports_real_reason():
    ok, reason = tier3_paddle.backend_available()
    assert ok is False
    assert reason  # not empty — must say *why*, not just "no"


def test_read_raises_capability_unavailable_not_a_silent_mock(tmp_path):
    with pytest.raises(tier3_paddle.CapabilityUnavailable):
        tier3_paddle.read(tmp_path / "x.pdf", [1], {})


@pytest.mark.requires_gpu
def test_read_produces_bhumidocument_shape_on_workstation():
    """Placeholder for the workstation: once real weights + a real page
    image are available, assert the output is a valid BhumiDocument with
    tier=3 on every emitted element. Not implemented against a real model
    response — see tier3_paddle.py's docstring on why."""
    pytest.skip("write against a real workstation response before trusting this")
