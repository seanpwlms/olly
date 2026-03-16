"""Tests for the shared stats functions (compute_zscore, compute_ewma)."""

from olly.checks.stats import compute_ewma, compute_zscore


def test_zscore_basic():
    history = [10.0, 10.0, 10.0, 10.0, 10.0]
    score = compute_zscore(20.0, history)
    assert score is not None
    assert score > 0


def test_zscore_too_short():
    assert compute_zscore(10.0, [5.0]) is None
    assert compute_zscore(10.0, []) is None


def test_zscore_zero_stdev_same_value():
    assert compute_zscore(5.0, [5.0, 5.0, 5.0]) is None


def test_zscore_zero_stdev_different_value():
    score = compute_zscore(10.0, [5.0, 5.0, 5.0])
    assert score == 1e6


def test_ewma_basic():
    history = [10.0, 10.0, 10.0, 10.0, 10.0]
    score = compute_ewma(50.0, history)
    assert score is not None
    assert score > 0


def test_ewma_too_short():
    assert compute_ewma(10.0, [5.0]) is None
    assert compute_ewma(10.0, []) is None


def test_ewma_float_values():
    history = [1.5, 1.6, 1.4, 1.55, 1.45]
    score = compute_ewma(1.5, history)
    # Normal variation — should be small or None
    assert score is None or abs(score) < 3.0


def test_ewma_spike_detected():
    history = [10.0, 10.0, 10.0, 10.0, 10.0]
    score = compute_ewma(100.0, history)
    assert score is not None
    assert score > 3.0
