import asyncio
import pytest
from aura.reasoning_benchmark import compare_methods, grade_case, validate_suite

SUITE={'dev':[{'id':'d1','question':'Qual a soma dos ângulos?','reference':'180 graus','gold_evidence_ids':['p:1'],'answerable':True},
              {'id':'d2','question':'Como é a temperatura no Sol?','reference':'','gold_evidence_ids':[],'answerable':False}],
       'test':[{'id':'t1','question':'Quanto vale a soma?','reference':'180 graus','gold_evidence_ids':['p:2'],'answerable':True}]}

def test_suite_is_held_out_and_unique():
    assert len(validate_suite(SUITE))==64
    bad={**SUITE,'test':[dict(SUITE['dev'][0])]}
    with pytest.raises(ValueError):validate_suite(bad)

def test_abstention_is_strict():
    item=SUITE['dev'][1]
    assert grade_case(item,{'answer':'','evidence_ids':[],'abstained':True})['score']==1
    assert grade_case(item,{'answer':'Desconhecido','evidence_ids':[],'abstained':True})['score']==0

def test_hallucinated_reference_blocks_full_score():
    x=grade_case(SUITE['dev'][0],{'answer':'180 graus','evidence_ids':['inventado'],'abstained':False})
    assert x['score']<.6

async def baseline(q):return {'answer':'','evidence_ids':[],'abstained':True}
async def candidate(q):
    if 'Sol' in q:return {'answer':'','evidence_ids':[],'abstained':True}
    return {'answer':'180 graus','evidence_ids':['p:1' if 'ângulos' in q else 'p:2'],'abstained':False}

def test_candidate_recommendation_and_no_gold_leakage():
    async def no_gold(q):
        assert isinstance(q,str) and 'gold_evidence_ids' not in q
        return await candidate(q)
    r=asyncio.run(compare_methods(SUITE,baseline,no_gold))
    assert r['recommendation']=='candidate_for_human_review'
    assert r['test_gain']>0

def test_overfit_rejected_even_if_dev_wins():
    async def overfit(q):
        if 'Quanto' in q:return await baseline(q)
        return await candidate(q)
    async def strong_test(q):
        if 'Quanto' in q:return await candidate(q)
        return await baseline(q)
    r=asyncio.run(compare_methods(SUITE,strong_test,overfit))
    assert r['dev_gain']>0
    assert r['test_gain']<0
    assert r['recommendation']=='retain_baseline'
