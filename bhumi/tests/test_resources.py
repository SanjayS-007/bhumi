"""Resource-budget admission check (base design §7). Availability is
injected rather than read from real psutil/torch so the test is
deterministic regardless of what machine it runs on.
"""
from bhumi.runtime.resources import check_admission


def test_admits_when_everything_fits():
    result = check_admission(
        "sqlite", ["embeddings_bge_small"],
        available_ram_gb=8.0, available_vram_gb=0.0,
    )
    assert result.admitted
    assert result.estimated_ram_gb == 0.5


def test_rejects_when_ram_exceeds_available():
    result = check_admission(
        "workstation", ["narrative_llm_qwen25_3b", "entailment_minicheck", "paddleocr_vl"],
        available_ram_gb=2.0, available_vram_gb=8.0,
    )
    assert not result.admitted
    assert "RAM" in result.reason


def test_rejects_when_vram_exceeds_the_profile_budget():
    # workstation's budget in config/resources.yaml is 6.0 GB VRAM;
    # paddleocr_vl alone costs 4.0 -- three of them exceed the budget
    # even though this fake machine claims plenty of available VRAM
    result = check_admission(
        "workstation", ["paddleocr_vl", "paddleocr_vl"],
        available_ram_gb=32.0, available_vram_gb=32.0,
    )
    assert not result.admitted
    assert "budget" in result.reason


def test_explicit_settings_override_wins_over_profile_default():
    result = check_admission(
        "workstation", ["embeddings_bge_small"],
        max_vram_gb=0.1,  # override far below the profile's normal 6.0 GB budget
        available_ram_gb=32.0, available_vram_gb=32.0,
    )
    assert not result.admitted
