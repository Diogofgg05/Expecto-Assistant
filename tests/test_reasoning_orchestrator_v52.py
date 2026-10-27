import asyncio
import pytest
from aura.reasoning_orchestrator import ReasoningOrchestrator, LocalSearxngSearch, OrchestrationConfig, _web_evidence
from aura.training_lab import prepare_training_data


class StubResearch:
    def __init__(self, evidence=None):
        self.ev = evidence if evidence is not None else [
            {'passage_id':'id-1','book_id':'book-1','title':'Álgebra Linear', 'page':6,
             'text':'Em álgebra linear o determinante permite avaliar se uma matriz quadrada é invertível.',
             'text_hash':'h1','verified_against_index':True}]
        self.queries=[]

    async def investigate(self, questions, **kwargs):
        self.queries=questions
        return {'evidence':self.ev}


class FakeModel:
    def __init__(self, answer=None, queries=None):
        self.answer=answer or {'answer':'O determinante permite avaliar se uma matriz quadrada é invertível.',
                               'citations':['p:id-1'],'calculations':[], 'uncertainties':[]}
        self.queries=queries if queries is not None else ['quando uma matriz é invertível?']
        self.calls=[]

    async def __call__(self, prompt):
        import json
        request=json.loads(prompt)
        self.calls.append(request)
        return {'queries':self.queries} if len(self.calls)==1 else self.answer


class FakeWeb:
    def __init__(self): self.calls=[]
    async def search(self, query, limit=5):
        self.calls.append(query)
        return [{'url':'https://example.org/algebra','title':'Algebra','content':'A matriz quadrada tem determinante.'}]


def go(obj, **kwargs): return asyncio.run(obj.run('Quando o determinante indica invertibilidade?',**kwargs))


def test_hybrid_research_and_cited_answer():
    model=FakeModel(); stub=StubResearch();r=go(ReasoningOrchestrator(None,model,research=stub))
    assert r['status']=='supported_proposal'
    assert r['citations']==['p:id-1']
    assert r['evidence'][0]['page']==6
    assert len(stub.queries)==2
    assert r['audits']['claim']['semantic_entailment_verified'] is False


def test_no_evidence_never_calls_answer_generation():
    model=FakeModel(); r=go(ReasoningOrchestrator(None,model,research=StubResearch([])))
    assert r['status']=='abstained' and len(model.calls)==1


def test_fabricated_citation_rejected():
    model=FakeModel({'answer':'inventado','citations':['p:fake']})
    r=go(ReasoningOrchestrator(None,model,research=StubResearch()))
    assert r['status']=='abstained' and not r['answer']


def test_wrong_calculation_suppressed():
    model=FakeModel({'answer':'Em álgebra linear o determinante indica que 125+75=201.',
                     'citations':['p:id-1'],'calculations':[{'expression':'125+75','asserted_result':'201'}]})
    r=go(ReasoningOrchestrator(None,model,research=StubResearch()))
    assert r['status']=='requires_revision' and r['audits']['arithmetic']['checks'][0]['status']=='refuted_arithmetic'
    assert not r['answer']


def test_unsupported_number_is_flagged():
    model=FakeModel({'answer':'A matriz quadrada tem determinante igual a 7000.', 'citations':['p:id-1']})
    r=go(ReasoningOrchestrator(None,model,research=StubResearch()))
    assert r['status']=='requires_revision'


def test_untrusted_web_snippet_marked_without_proof():
    web=FakeWeb(); model=FakeModel({'answer':'A matriz quadrada tem determinante.',
                                   'citations':['w:df3a'],'calculations':[]})
    # Use exact computed trusted URL ID for the test.
    model.answer['citations']=[_web_evidence({'url':'https://example.org/algebra','title':'Algebra',
                                            'content':'A matriz quadrada tem determinante.'})['id']]
    r=go(ReasoningOrchestrator(None,model,external=web,research=StubResearch([])))
    assert r['status']=='supported_proposal' and r['audits']['web_only'] is True
    assert any(e['kind']=='web_snippet' for e in r['evidence'])
    assert r['verified']=='none' and web.calls


def test_external_disabled_by_default():
    model=FakeModel(); web=FakeWeb()
    go(ReasoningOrchestrator(None,model,research=StubResearch()))
    assert not web.calls


def test_external_requires_loopback():
    for url in ('https://example.com:9999','http://0.0.0.0:9999','http://127.0.0.1:8888/a',
                'http://test:password@127.0.0.1:8888', 'http://127.0.0.1'):
        with pytest.raises(ValueError): LocalSearxngSearch(url)
    assert LocalSearxngSearch('http://127.0.0.1:8888').base_url=='http://127.0.0.1:8888'


def test_web_url_sanitization():
    assert _web_evidence({'url':'javascript:alert(1)','title':'bad','content':'x'}) is None
    assert _web_evidence({'url':'https://example.org', 'title':'', 'content':'x'}) is None


def test_bad_research_query_falls_back():
    model=FakeModel(queries=['x',''*10,'when is determinant valid?']*5)
    r=go(ReasoningOrchestrator(None,model,research=StubResearch()))
    assert len(r['research_queries'])==2


def samples(n=5,dpo=False):
    return [{'prompt':'Pergunta totalmente inédita '+str(i),'chosen':'Resposta correta '+str(i),
             'rejected':'Resposta incorreta '+str(i) if dpo else None,
             'rights':'authorized_for_model_training','human_reviewed':True,
             'contains_personal_data':False} for i in range(n)]


def test_training_requires_consent_rights_and_review(tmp_path):
    with pytest.raises(PermissionError):
        prepare_training_data(samples(5),tmp_path/'no',format='sft')
    data=samples(5);data[0]['human_reviewed']=False
    with pytest.raises(PermissionError):
        prepare_training_data(data,tmp_path/'no',format='sft',user_authorized=True)
    assert not (tmp_path/'no').exists()


def test_training_sft_split_no_auto_training(tmp_path):
    r=prepare_training_data(samples(10),tmp_path/'train',format='sft',user_authorized=True)
    assert r['counts']=={'train':8,'validation':1,'holdout':1}
    assert r['training_executed'] is False
    assert (tmp_path/'train'/'holdout.jsonl').exists()
    with pytest.raises(FileExistsError):
        prepare_training_data(samples(10),tmp_path/'train',format='sft',user_authorized=True)


def test_training_dpo_and_duplicate_guard(tmp_path):
    r=prepare_training_data(samples(3,True),tmp_path/'dpo',format='dpo',user_authorized=True)
    assert r['counts']['holdout']==1
    data=samples(3);data[1]['prompt']=data[0]['prompt'].upper()
    with pytest.raises(ValueError):
        prepare_training_data(data,tmp_path/'duplicate',format='sft',user_authorized=True)


def test_training_requires_explicit_rights(tmp_path):
    data=samples(4);data[0]['rights']='CC-BY-NC reading only'
    with pytest.raises(PermissionError):
        prepare_training_data(data,tmp_path/'bad',format='sft',user_authorized=True)


def test_full_pipeline_with_real_generated_pdf_and_sqlite(tmp_path):
    fitz=pytest.importorskip('fitz')
    from aura.database import Database
    from aura.books import BookLearningEngine
    db=Database(tmp_path/'aura.sqlite3',require_encryption=False)
    pdf=tmp_path/'matematica.pdf'
    with fitz.open() as d:
        page=d.new_page()
        page.insert_text((40,80),'O determinante de uma matriz quadrada permite avaliar se ela e invertivel.')
        d.save(pdf)
    book=BookLearningEngine(db).import_pdf(pdf,rights_confirmed=True,
            rights_note='PDF sintético criado para teste')
    model=FakeModel({'answer':'O determinante de uma matriz quadrada permite avaliar se ela e invertivel.',
                     'citations':[]},queries=[])
    class SourceAware:
        async def __call__(self,prompt):
            import json
            p=json.loads(prompt)
            if 'question' in p and 'evidence' not in p: return {'queries':[]}
            assert p['evidence'][0]['page']==1
            return {'answer':p['evidence'][0]['text'],
                    'citations':[p['evidence'][0]['id']], 'calculations':[]}
    result=go(ReasoningOrchestrator(db,SourceAware()),book_id=book['book_id'])
    assert result['status']=='supported_proposal'
    assert result['evidence'][0]['page']==1
    assert result['citations'][0].startswith('p:')


def test_ollama_offline_fails_closed():
    import httpx
    class Offline:
        async def __call__(self, prompt):
            raise httpx.ConnectError('offline')
    result=go(ReasoningOrchestrator(None,Offline(),research=StubResearch()))
    assert result['status']=='abstained'
    assert result['answer']==''
    assert any('Modelo não produziu' in x for x in result['limitations'])
