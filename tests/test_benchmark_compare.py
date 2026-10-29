"""Regression policy unit tests using synthetic benchmark reports."""
from copy import deepcopy
from aura.benchmark_compare import compare


def report(ms=100.0, rate=50.0, model="qwen3"):
    return {
        "model": model, "url": "http://127.0.0.1:11434",
        "streaming": False, "python": "3.12", "platform": "test-host",
        "runs": 20, "samples": [{} for _ in range(20)],
        "summary": {
            "elapsed_ms": {"samples": 20, "p50": ms, "p95": ms * 1.2},
            "tokens_per_second": {"samples": 20, "p50": rate, "p95": rate},
        },
    }


def test_faster_candidate_needs_review():
    result = compare(report(), report(ms=90))
    assert result["decision"] == "candidate_for_review"
    assert result["metrics"]["elapsed_ms"]["p95_change_pct"] == -10.0


def test_reject_latency_regression():
    result = compare(report(), report(ms=110))
    assert result["decision"] == "reject"
    assert result["metrics"]["elapsed_ms"]["regression"]


def test_reject_throughput_regression():
    result = compare(report(), report(ms=90, rate=40))
    assert result["decision"] == "reject"


def test_different_model_is_inconclusive():
    assert compare(report(), report(model="other"))["decision"] == "inconclusive"


def test_missing_samples_cannot_be_approved():
    candidate = report(ms=50)
    candidate["samples"] = candidate["samples"][:2]
    assert compare(report(), candidate)["decision"] == "inconclusive"


def test_invalid_threshold_rejected():
    import pytest
    with pytest.raises(ValueError):
        compare(report(), report(), max_regression_pct=-1)


def test_equal_results_are_inconclusive():
    assert compare(report(), deepcopy(report()))["decision"] == "inconclusive"
