import asyncio
import pytest
from aura.reasoning_verifier import exact_arithmetic, VerificationError, check_calculations, ReasoningVerifier

def test_exact():
    assert exact_arithmetic('125 + 75') == '200'
    assert exact_arithmetic('(2 + 3) / 2') == '5/2'
    assert exact_arithmetic('-5 * 3') == '-15'

@pytest.mark.parametrize('s', ['__import__("os")','2**20000000','1/0','2.5','2//1','3 > 2','9'*500,'abs(2)'])
def test_restrict(s):
    with pytest.raises(VerificationError): exact_arithmetic(s)

def test_refute():
    x=check_calculations([{'expression':'125 + 75','asserted_result':'201'}])
    assert x['checks'][0]['status']=='refuted_arithmetic'
    assert x['checks'][0]['computed_result']=='200'

def test_confirm():
    x=check_calculations([{'expression':'1/3 + 1/6','asserted_result':'1/2'}])
    assert x['all_confirmed']

def test_bad_source_rejected():
    async def model(_):
        return {'answer':'hello','evidence_ids':['fake'],'calculations':[]}
    x=asyncio.run(ReasoningVerifier(model).run('Questão?', [{'id':'real','text':'Hello.'}],critique=False))
    assert x['status']=='abstained'

def test_math_caught_and_critic():
    async def model(prompt):
        if 'Critique the answer' in prompt:return {'objections':['Verificar os dados de entrada.']}
        return {'answer':'201','evidence_ids':['p1'],'calculations':[{'expression':'125+75','asserted_result':'201'}]}
    x=asyncio.run(ReasoningVerifier(model).run('Quanto?', [{'id':'p1','text':'125 unidades + 75 unidades'}]))
    assert 'Cálculo refutado' in x['limitations'] and x['status']=='review_required' and x['objections']

def test_no_source_does_not_prove():
    async def model(_):return {'answer':'5','evidence_ids':[],'calculations':[{'expression':'2+3','asserted_result':'5'}]}
    x=asyncio.run(ReasoningVerifier(model).run('Pergunta?',[],critique=False))
    assert x['verified']=='arithmetic_only' and x['status']=='review_required'
