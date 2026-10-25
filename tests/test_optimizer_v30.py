"""Offline tests of the gated reasoning lab; do not need DSPy/Ollama/SQLCipher."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
import pytest
from aura.config import Settings
from aura.database import Database
from aura.optimizer import OptimizationLab, clean, metric_score, evidence_tokens, load_benchmark, BENCHMARK
from aura.engine import AuraEngine
from aura.app import create_app


def prepare(tmp_path):
    settings=Settings(data_dir=tmp_path, database_encryption_required=False)
    db=Database(tmp_path/'aura.sqlite3')
    return settings, db, OptimizationLab(settings,db)


def stage(lab, **kwargs):
    args=dict(method='labeled', model='hermes3',
              data_hash=hashlib.sha256(BENCHMARK.read_bytes()).hexdigest(),
              baseline_dev=0.25,candidate_dev=0.75,baseline_test=0.20,candidate_test=1.0,
              artifact_bytes=json.dumps({'predict':{'demos':[]}}).encode())
    args.update(kwargs)
    return lab.stage(**args)


def test_metric_needs_exact_answer_and_right_citation():
    gold=SimpleNamespace(answer='LISBOA', source_id='D02')
    assert metric_score(gold, SimpleNamespace(answer='Lisboa',source_ids='D02')) == 1
    assert metric_score(gold, SimpleNamespace(answer='Lisboa',source_ids='D01')) == 0
    assert metric_score(gold, SimpleNamespace(answer='Lisboa',source_ids='D01, D02')) == 0
    assert metric_score(gold, SimpleNamespace(answer='Porto',source_ids='D02')) == 0
    assert clean(' memÓria ')=='memoria'
    assert evidence_tokens('D01, D02')=={'D01','D02'}


def test_benchmark_disjoint_and_adequate():
    splits=load_benchmark()
    assert len(splits['train'])>=5 and len(splits['dev'])>=3 and len(splits['test'])>=5
    ids=[r['id'] for group in splits.values() for r in group]
    assert len(set(ids))==len(ids)
    assert {'D01','D02'} == evidence_tokens(splits['test'][0]['evidence'])


def test_stage_manual_approve_and_rollback(tmp_path):
    settings,db,lab=prepare(tmp_path)
    db.add_memory('Prefiro uma AURA sem botões.')
    trial=stage(lab)
    assert trial['eligible'] and trial['state']=='staged'
    assert lab.status()['active'] is None
    assert lab.approve(trial['id'])
    assert lab.status()['active']['id']==trial['id']
    assert lab.rollback()
    assert lab.status()['active'] is None
    assert db.memories()[0]['content']=='Prefiro uma AURA sem botões.'
    assert not lab.approve(trial['id'])  # cannot activate retired candidate silently


def test_reject_no_improvement_tamper_and_model_change(tmp_path):
    settings,db,lab=prepare(tmp_path)
    bad=stage(lab, candidate_test=0.50)
    assert not bad['eligible']
    assert not lab.approve(bad['id'])
    good=stage(lab)
    lab._artifact(good['id']).write_bytes(b'{}')
    assert not lab.approve(good['id'])
    assert lab.get(good['id'])['artifact_intact'] is False
    changed=OptimizationLab(Settings(data_dir=tmp_path,ollama_model='other',database_encryption_required=False),db)
    assert not changed.approve(good['id'])


def test_reject_untrusted_benchmark_and_bad_artifact(tmp_path):
    settings,db,lab=prepare(tmp_path)
    with pytest.raises(ValueError):
        stage(lab,artifact_bytes=b'not json')
    with pytest.raises(ValueError):
        stage(lab,baseline_test=1.5)
    assert lab.status()['experiments']==[]


def test_migration_preserves_existing_notes_and_approvals(tmp_path):
    settings,db,lab=prepare(tmp_path)
    db.add_memory('Memória antiga de seis meses.')
    trial=stage(lab)
    reloaded=Database(tmp_path/'aura.sqlite3')
    lab_again=OptimizationLab(settings,reloaded)
    assert lab_again.get(trial['id'])['artifact_intact']
    assert reloaded.memories()[0]['content']=='Memória antiga de seis meses.'


def test_interface_command_api_no_training_without_explicit_cli(tmp_path):
    settings,db,lab=prepare(tmp_path)
    trial=stage(lab)
    engine=AuraEngine(settings,db)
    s=asyncio.run(engine.command('Estado do raciocínio'))
    assert 'experiências' in s['text']
    assert not engine.optimizer.status()['active']
    assert asyncio.run(engine.command('Responde com fontes sobre DNS'))['ok']
    assert asyncio.run(engine.command('Aprova otimização '+trial['id']))['ok']
    assert engine.optimizer.status()['active'] is not None
    assert asyncio.run(engine.command('Reverte estratégia'))['ok']
    assert engine.optimizer.status()['active'] is None
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/health').json()['version'].startswith('3.3')
        obj=client.get('/api/optimizer/status').json()
        assert obj['automatic_training'] is False
        assert not obj['active']
        assert client.get('/api/optimizer/run').status_code==404
        assert b'sidebar' not in client.get('/').content.lower()


def test_run_executes_candidate_evaluation_with_fake_local_model(tmp_path,monkeypatch):
    """No network; verifies train/dev/held-out/control flow, not model quality."""
    _,db,lab=prepare(tmp_path)
    calls=[]
    class Example:
        def __init__(self,**kw):self.__dict__.update(kw)
        def with_inputs(self,*args):return self
    class Predict:
        def __init__(self,signature,improved=False):self.improved=improved
        def __call__(self,question,evidence):
            # Fake returns wrong baseline; improved returns facts only from the
            # benchmark it was constructed from (never model validation).
            if not self.improved:return SimpleNamespace(answer='?',source_ids='D88')
            case=next(x for parts in load_benchmark().values() for x in parts if x['question']==question)
            return SimpleNamespace(answer=case['answer'],source_ids=case['source_id'])
        def save(self,path,save_program=False):Path(path).write_text(json.dumps({'improved':True}))
    class LabeledFewShot:
        def __init__(self,k):calls.append(('k',k))
        def compile(self,student,trainset,sample=False):
            calls.append(('train_length',len(trainset)))
            return Predict('x',improved=True)
    fake=SimpleNamespace(Example=Example,Predict=Predict,LabeledFewShot=LabeledFewShot,
                         LM=lambda *a,**kw:object(),configure=lambda **kw:None)
    monkeypatch.setattr(lab,'_dspy',lambda:fake)
    trial=lab.run('labeled')
    assert trial['candidate_dev']==1.0 and trial['candidate_test']==1.0
    assert trial['baseline_test']==0.0 and trial['eligible']
    assert calls[0][0]=='k' and calls[1]==('train_length',8)
