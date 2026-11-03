import pytest
from aura.laboratory_summary import choose_installed, distribution, summarize, environment


def test_selection_preserves_explicit_tags():
    assert choose_installed('qwen', ['qwen:latest','qwen:4b']) == 'qwen:latest'
    assert choose_installed('qwen:4b', ['qwen:4b','qwen:8b']) == 'qwen:4b'
    with pytest.raises(ValueError): choose_installed('qwen:missing', ['qwen:4b','qwen:8b'])
    with pytest.raises(ValueError): choose_installed('qwen', [])


def test_unavailable_memory_never_becomes_zero():
    rows=[{'profile':'eco','pipeline':'raw','correct':False,'ok':False,'total_ms':25,'calls':[{'resources':None}]}]
    summary=summarize(rows)[0]
    assert summary['failures']==1
    assert summary['call_sampled_peak_bytes']['loaded_vram_bytes']['median'] is None
    assert summary['response_total_ms']['median']==25


def test_distribution_ignores_invalid_measurements():
    assert distribution([None,float('nan'),-1,1,2,3]) == {'samples':3,'median':2,'p95':3}
    assert 'hostname' not in environment()
