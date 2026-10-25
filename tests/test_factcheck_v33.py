"""Fact verification: no truth certification, no arbitrary outbound fetches."""
import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.factcheck import FactChecker, fetch_wiki_excerpt, wikipedia_title, WIKI_API
from aura.learning import LearningEngine


def setup(tmp_path):
    settings=Settings(data_dir=tmp_path,database_encryption_required=False,
                      embedding_model='',auto_extract_memory=False)
    db=Database(tmp_path/'aura.sqlite3')
    return settings,db,LearningEngine(settings,db),FactChecker(db)


def add_claim(db, learning, url='https://pt.wikipedia.org/wiki/Aritmética',
              statement='125 + 75 = 200', topic='Matemática'):
    content=f'O documento afirma explicitamente que {statement} e apresenta o resultado.'
    d=db.remember_document(topic,'Fonte pública',content,url,'wikipedia','single_source')
    result=learning.record(topic,[d],[{'document_id':d['id'],'statement':statement,
                                        'exact_quote':content}])
    assert result.stored==1
    return next(c['id'] for c in learning.claims(topic) if c['statement']==statement)


@pytest.mark.parametrize('url',[
    'http://pt.wikipedia.org/wiki/Teste','https://evil.tld/wiki/Teste',
    'https://pt.wikipedia.org.evil.tld/wiki/Teste',
    'https://pt.wikipedia.org:444/wiki/Teste',
    'https://user@pt.wikipedia.org/wiki/Teste',
    'https://pt.wikipedia.org/w/api.php','https://pt.wikipedia.org/wiki/../Teste',
    'https://pt.wikipedia.org/wiki/Foo%2FBar',
    'https://pt.wikipedia.org/wiki/Teste?redirect=evil',
    'https://pt.wikipedia.org/wiki/Teste#section',
    'https://127.0.0.1/wiki/Teste',
])
def test_strict_wikipedia_allowlist_blocks_unsafe_urls(url):
    assert wikipedia_title(url) is None


def test_only_wikipedia_title_is_extracted():
    assert wikipedia_title('https://pt.wikipedia.org/wiki/Teoria_dos_números')=='Teoria dos números'
    assert wikipedia_title('https://pt.wikipedia.org/wiki/Espa%C3%A7o')=='Espaço'


def test_archived_claims_are_not_promoted_to_truth(tmp_path):
    _,db,learning,checker=setup(tmp_path)
    claim=add_claim(db,learning)
    result=checker.offline(claim)
    assert result['fact_proven'] is False
    assert result['independence_established'] is False
    assert result['grade']=='archived_reporting_only'
    assert result['live_attempted'] is False
    assert checker.latest()==[]


def test_two_different_hosts_are_not_editorial_independence(tmp_path):
    _,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning, url='https://one.example.org/a')
    add_claim(db,learning,url='https://two.example.com/b')
    result=checker.offline(cid)
    assert result['unique_hosts_with_intact_snapshots']==2
    assert result['identical_reporting_possible'] is True
    assert not result['independence_established']
    assert not result['fact_proven']


def test_live_wiki_recheck_is_bounded_and_preserves_claims(tmp_path, monkeypatch):
    settings,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning)
    from aura import factcheck
    calls=[]
    class StubResponse:
        is_redirect=False
        content=b'{}'
        def raise_for_status(self):pass
        def json(self):return {'query':{'pages':[{'title':'Aritmética',
                'extract':'O documento afirma explicitamente que 125 + 75 = 200 e apresenta o resultado.'}]}}
    class StubClient:
        def __init__(self,**kwargs):
            assert kwargs['follow_redirects'] is False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,params):
            calls.append((url,params))
            return StubResponse()
    monkeypatch.setattr(factcheck.httpx,'AsyncClient',StubClient)
    result=asyncio.run(checker.verify_live(cid))
    assert len(calls)==1 and calls[0][0]==WIKI_API
    assert calls[0][1]['titles']=='Aritmética'
    assert result['grade']=='source_quote_observed_live'
    assert result['fact_proven'] is False
    assert result['independence_established'] is False
    assert result['live_supported_sources']==1
    assert len(checker.latest())==1
    assert result['evidence'][0]['live_excerpt_sha256']
    assert learning.claims('Matemática')[0]['state']=='single_source'


def test_no_arbitrary_network_for_unapproved_host(tmp_path,monkeypatch):
    _,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning,url='https://publisher.example.net/page')
    from aura import factcheck
    class MustNotStart:
        def __init__(self,*args,**kwargs):
            raise AssertionError('Não abrir clientes HTTP para sites não permitidos.')
    monkeypatch.setattr(factcheck.httpx,'AsyncClient',MustNotStart)
    result=asyncio.run(checker.verify_live(cid))
    assert result['grade']=='no_approved_live_provider'
    assert result['evidence'][0]['live_status']=='provider_not_supported'
    assert checker.latest()==[]


def test_compromised_archive_blocks_external_recheck(tmp_path, monkeypatch):
    _,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning)
    with db.connect() as conn:
        conn.execute('UPDATE knowledge SET content=?',('Alterado.',))
    from aura import factcheck
    monkeypatch.setattr(factcheck.httpx,'AsyncClient',lambda *a,**kw:
                        (_ for _ in ()).throw(AssertionError('must not open HTTP')))
    result=asyncio.run(checker.verify_live(cid))
    assert result['grade']=='blocked'
    assert checker.latest()==[]


def test_live_absence_is_uncertainty_not_falsity(tmp_path,monkeypatch):
    _,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning)
    from aura import factcheck
    async def mock_check(client,title):
        return factcheck.LiveExcerpt('available', 'a'*64, 'Texto novo que não contém a citação.')
    monkeypatch.setattr(factcheck,'fetch_wiki_excerpt',mock_check)
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(factcheck.httpx,'AsyncClient',Client)
    result=asyncio.run(checker.verify_live(cid))
    assert result['grade']=='source_not_confirmed_live'
    assert result['evidence'][0]['live_status']=='quote_not_found_in_intro'
    assert not result['fact_proven']


def test_limited_api_data_and_voice_command(tmp_path):
    settings,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning,url='https://news.example.net/story')
    eng=AuraEngine(settings,db)
    result=asyncio.run(eng.command('AURA, analisa evidências externas '+cid))
    assert result['action']=={'type':'open','panel':'research'}
    assert result['data']['factcheck_report']['live_attempted'] is False
    result=asyncio.run(eng.command('AURA, verifica factos '+cid))
    assert result['data']['factcheck_report']['grade']=='no_approved_live_provider'
    with TestClient(create_app(settings)) as client:
        result=client.get('/api/factcheck/claims/'+cid)
        assert result.status_code==200
        assert result.json()['fact_proven'] is False
        assert client.get('/api/factcheck/claims/xyz').status_code==422
        assert client.get('/api/factcheck/claims/'+'f'*12).status_code==404
        assert client.get('/api/factcheck/history').json()=={'items':[]}
        assert client.get('/api/health').json()['version'].startswith('3.3')


def test_no_history_after_claim_deletion(tmp_path,monkeypatch):
    _,db,learning,checker=setup(tmp_path)
    cid=add_claim(db,learning)
    from aura import factcheck
    async def mock_check(*args):
        return factcheck.LiveExcerpt('available','a'*64,
            'O documento afirma explicitamente que 125 + 75 = 200 e apresenta o resultado.')
    monkeypatch.setattr(factcheck,'fetch_wiki_excerpt',mock_check)
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(factcheck.httpx,'AsyncClient',Client)
    asyncio.run(checker.verify_live(cid))
    assert checker.latest()
    with db.connect() as conn:conn.execute('DELETE FROM learning_claims WHERE id=?',(cid,))
    assert checker.latest()==[]


def test_wiki_http_error_and_redirect_fail_closed():
    async def run_response(payload, status=200, headers=None):
        def handler(req):return httpx.Response(status_code=status,json=payload,headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_wiki_excerpt(client,'Matemática')
    assert asyncio.run(run_response({'query':{'pages':[]}})).state=='unavailable'
    assert asyncio.run(run_response({'query':{'pages':[{'missing':True}]}})).state=='unavailable'
    assert asyncio.run(run_response({},status=429)).state=='unavailable'
    assert asyncio.run(run_response({},status=302,headers={'location':'http://127.0.0.1'})).state=='unavailable'
