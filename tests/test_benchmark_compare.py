"""Unit checks for fail-closed benchmark comparison using synthetic reports."""
from copy import deepcopy
import pytest
from aura.benchmark_compare import compare


def report(ms=100, rate=50, model='qwen3'):
    return {'model': model, 'url': 'http://127.0.0.1:11434', 'streaming': False,
            'python': '3.12', 'platform': 'test-host', 'runs': 20,
            'samples': [{'elapsed_ms': ms, 'tokens_per_second': rate}
                        for _ in range(20)],
            'summary': {'elapsed_ms': {'p50': 1, 'p95': 1}}}


def test_faster():
    assert compare(report(), report(ms=90))['decision'] == 'candidate_for_review'


def test_slower():
    assert compare(report(), report(ms=110))['decision'] == 'reject'


def test_throughput_regression():
    assert compare(report(), report(ms=90, rate=40))['decision'] == 'reject'


def test_different_model():
    assert compare(report(), report(model='other'))['decision'] == 'inconclusive'


def test_missing_samples():
    candidate = report(ms=50)
    candidate['samples'] = candidate['samples'][:2]
    assert compare(report(), candidate)['decision'] == 'inconclusive'


def test_invalid_threshold():
    with pytest.raises(ValueError):
        compare(report(), report(), max_regression_pct=float('nan'))


def test_equal():
    assert compare(report(), deepcopy(report()))['decision'] == 'inconclusive'


def test_fake_summary_not_trusted():
    candidate = report(ms=120)
    candidate['summary'] = {'elapsed_ms': {'p50': 1, 'p95': 1}}
    assert compare(report(), candidate)['decision'] == 'reject'


def test_nonfinite_rejected():
    candidate = report(ms=90)
    candidate['samples'][3]['elapsed_ms'] = float('nan')
    assert compare(report(), candidate)['decision'] == 'inconclusive'


def test_missing_throughput_does_not_block_latency():
    before, after = report(), report(ms=80)
    for row in before['samples'] + after['samples']:
        row.pop('tokens_per_second')
    assert compare(before, after)['decision'] == 'candidate_for_review'
