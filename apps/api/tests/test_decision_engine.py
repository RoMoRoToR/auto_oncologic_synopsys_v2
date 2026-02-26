import math

from apps.api.decision_engine import (
    normalize_cv,
    choose_design,
    compute_washout_days,
    sample_size,
    generate_timeline,
)


def test_normalize_cv():
    assert normalize_cv("25") == 0.25
    assert normalize_cv("0.25") == 0.25
    assert normalize_cv("25%") == 0.25


def test_choose_design():
    assert choose_design(False, 0.2)["design"] == "2x2"
    assert choose_design(False, 0.35)["design"] == "replicate"
    assert choose_design(True, 0.1)["design"] == "replicate"


def test_compute_washout_days():
    assert compute_washout_days(None) == 7
    assert compute_washout_days(10) >= 7


def test_sample_size_monotonic():
    s1 = sample_size(0.2)
    s2 = sample_size(0.3)
    assert s2["n_required"] >= s1["n_required"]


def test_generate_timeline_horizon():
    t = generate_timeline(4, 20)
    assert t["sampling_horizon_h"] >= 80
    assert 4 in t["timepoints_h"]
