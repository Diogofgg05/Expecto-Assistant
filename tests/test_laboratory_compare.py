from copy import deepcopy
import pytest
from aura.laboratory_compare import compare_reports


def fixture():
    return {'complete':True,'corpus_sha256':'same','repeats':2,'warmup':0,'rows':[
        {'case_id':'a','repeat':0,'profile':'eco','effective_profile':'eco','pipeline':'raw','ok':True,'correct':True,'total_ms':100}]}


def test_faster_wrong_answer_never_improves():
    a=fixture(); b=deepcopy(a); b['rows'][0].update(total_ms=50, correct=False)
    r=compare_reports(a,b)['comparisons'][0]
    assert r['paired_accuracy_losses']==1
    assert not r['observed_improvement_without_paired_loss']


def test_same_quality_faster_report():
    a=fixture(); b=deepcopy(a); b['rows'][0]['total_ms']=50
    assert compare_reports(a,b)['comparisons'][0]['latency_change_pct']==-50


@pytest.mark.parametrize('change', ['corpus','incomplete','duplicate','nan'])
def test_refuses_invalid_comparisons(change):
    a=fixture(); b=deepcopy(a)
    if change=='corpus': b['corpus_sha256']='other'
    if change=='incomplete': b['complete']=False
    if change=='duplicate': b['rows']*=2
    if change=='nan': b['rows'][0]['total_ms']=float('nan')
    with pytest.raises(ValueError): compare_reports(a,b)
