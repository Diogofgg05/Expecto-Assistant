import asyncio
import json
from pathlib import Path
import pytest
from aura.multilayer_reasoning import MultiLayerReasoner,export_graph_html

class FakeResearch:
    async def investigate(self,*args,**kwargs):
        return {'evidence':[{'passage_id':'1','book_id':'b','title':'Livro','page':3,
                 'text':'A soma dos ângulos internos de um triângulo euclidiano é 180 graus.',
                 'text_hash':'abc'}]}

class FakeDB:
    pass

def make():
    obj=MultiLayerReasoner(FakeDB());obj.research=FakeResearch();return obj

async def good(prompt):
    return {'hypotheses':[{'claim':'Um triângulo euclidiano tem 180 graus.',
             'evidence_ids':['p:1'],'objection':'Geometrias não euclidianas não seguem esta regra.'}]}

def test_5_layers():
    result=asyncio.run(make().reason('O que acontece nos triângulos?',good))
    assert result['verified']=='provenance_only'
    assert len(result['graph']['nodes'])==5
    assert {n['layer'] for n in result['graph']['nodes']}==set(range(5))
    assert result['layers'][1]['items'][0]['evidence_ids']==['p:1']

def test_invalid_source_never_promoted():
    async def bogus(_):return {'hypotheses':[{'claim':'Invenção','objection':'Talvez','evidence_ids':['p:fake']}]}
    result=asyncio.run(make().reason('O que acontece nos triângulos?',bogus))
    assert result['verified']=='none' and not result['layers'][-1]['items']

def test_non_json_returns_uncertainty():
    async def garbage(_):return 'not-json'
    result=asyncio.run(make().reason('O que acontece nos triângulos?',garbage))
    assert result['verified']=='none' and result['limitations']

def test_no_sources_refuses():
    async def never(_):raise AssertionError('Model must not be called')
    class NoEvidence:
        async def investigate(self,*a,**kw):return {'evidence':[]}
    obj=make();obj.research=NoEvidence()
    result=asyncio.run(obj.reason('O que acontece nos triângulos?',never))
    assert result['verified']=='none'

def test_3d_html_escapes_content():
    html=export_graph_html({'nodes':[{'id':'a','layer':0,'label':'</script><script>alert(1)</script>'}],'links':[]})
    assert '</script><script>alert(1)' not in html
    assert 'ForceGraph3D' in html

def test_limits():
    with pytest.raises(ValueError):asyncio.run(make().reason('Pergunta válida',good,evidence_limit=50))
