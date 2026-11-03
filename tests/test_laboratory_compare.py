from copy import deepcopy
import pytest
from aura.laboratory_compare import compare_reports


def fixture():
    return {'complete':True,'corpus_sha256':'a'*64,'case_count':12,'repeats':2,'warmup':0,'rows':[
        {'case_id':str(i),'domain':('math','programming','research')[i%3], 'repeat':r,
         'profile':p,'effective_profile':p,'pipeline':'raw','ok':True,'correct':True,'total_ms':100}
        for p in ('eco','balanced','max') for i in range(12) for r in range(2)]}



def test_faster_wrong_answer_never_improves():
    a=fixture(); b=deepcopy(a); b['rows'][0].update(total_ms=50, correct=False)
    r=next(r for r in compare_reports(a,b)['comparisons'] if r['profile']=='eco')
    assert r['paired_accuracy_losses']==1
    assert not r['observed_improvement_without_paired_loss']


def test_same_quality_faster_report():
    a=fixture(); b=deepcopy(a)
    for row in b['rows']: row['total_ms']=50
    assert compare_reports(a,b)['comparisons'][0]['latency_change_pct']==-50


@pytest.mark.parametrize('change', ['corpus','incomplete','duplicate','nan'])
def test_refuses_invalid_comparisons(change):
    a=fixture(); b=deepcopy(a)
    if change=='corpus': b['corpus_sha256']='other'
    if change=='incomplete': b['complete']=False
    if change=='duplicate': b['rows']*=2
    if change=='nan': b['rows'][0]['total_ms']=float('nan')
    with pytest.raises(ValueError): compare_reports(a,b)


def test_confidence_requires_enough_independent_cases():
    a=fixture(); b=deepcopy(a)
    for row in b['rows']: row['total_ms']=50
    result=compare_reports(a,b)['comparisons'][0]
    assert result['speed_evidence']=='consistent_gain_over_5pct'
    assert result['paired_change_interval']['high']==-50


@pytest.mark.parametrize('defect',['boolean_latency','string_flag','missing_repeat','wrong_count'])
def test_untrusted_reports_fail_closed(defect):
    a=fixture(); b=deepcopy(a)
    if defect=='boolean_latency': b['rows'][0]['total_ms']=True
    if defect=='string_flag': b['rows'][0]['correct']='false'
    if defect=='missing_repeat': b['rows'].pop()
    if defect=='wrong_count': b['case_count']=13
    with pytest.raises(ValueError): compare_reports(a,b)
