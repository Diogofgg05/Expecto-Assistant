import asyncio
from aura.evidence_critic import audit_claim
from aura.multilayer_reasoning import MultiLayerReasoner


def test_flags_invented_numbers():
    result=audit_claim('A eficiência é 92%', ['O manual diz que a eficiência é 81%.'])
    assert 'numbers_absent_from_sources' in result['flags']
    assert result['semantic_entailment_verified'] is False


def test_flags_obvious_negation():
    result=audit_claim('O motor não funciona com energia solar', ['O motor funciona com energia solar'])
    assert 'negation_not_present_in_sources' in result['flags']


def test_no_false_proof_from_surface_checks():
    result=audit_claim('O motor utiliza energia solar', ['O motor utiliza energia solar'])
    assert result['status']=='surface_checks_passed_not_verified'


def test_multilayer_marks_unsupported_claim():
    class Source:
        async def investigate(self,*a,**kw):
            return {'evidence':[{'passage_id':'9','book_id':'b','title':'Manual','page':2,'text':'A potência indicada é 10 watts.','text_hash':'h'}]}
    class DB:pass
    async def model(prompt):return {'hypotheses':[{'claim':'A potência indicada é 900 watts','objection':'Pode haver erro','evidence_ids':['p:9']}]}
    r=MultiLayerReasoner(DB());r.research=Source()
    output=asyncio.run(r.reason('Qual a potência?',model))
    h=output['layers'][1]['items'][0]
    assert h['status']=='hypothesis_requires_review'
    assert output['audit_summary']['review_needed']==1
