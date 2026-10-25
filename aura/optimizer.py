"""AURA 3.0: opt-in DSPy evaluation lab for *evidence-grounded* short answers.

DSPy is an optional dependency. No training happens on app startup or in a
background daemon. Runs use only the bundled PUBLIC, artificial benchmark.
Candidate weights/prompts are staged separately; human approval is required.
No private conversations, knowledge or keys are submitted to an optimizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import unicodedata
from pathlib import Path
from uuid import uuid4
from .database import now
from .config import Settings, ROOT

BENCHMARK = ROOT / 'benchmarks' / 'grounded_qa_ptpt.json'
VALID_METHODS = {'labeled', 'bootstrap'}


def clean(text: object) -> str:
    """Exact-answer matching, ignoring accents, casing and punctuation."""
    s = unicodedata.normalize('NFKD', str(text or '').casefold())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', s))


def evidence_tokens(text: object) -> set[str]:
    """Citations must be exact IDs, separated by spaces/commas/semicolons."""
    return set(re.findall(r'[A-Z][0-9]{2}', str(text or '').upper()))


def metric_score(example, prediction, trace=None) -> float:
    """Strict held-out metric; correctness AND correct source attribution required.

    Does not establish factuality outside curated examples. Merely citing some
    existing source does not pass when that source is the wrong one.
    """
    expected = clean(getattr(example, 'answer', ''))
    actual = clean(getattr(prediction, 'answer', ''))
    expected_id = str(getattr(example, 'source_id', getattr(example, 'source_ids', ''))).upper()
    cited = evidence_tokens(getattr(prediction, 'source_ids', ''))
    return float(bool(expected and actual == expected and cited == {expected_id}))


def load_benchmark(path: Path = BENCHMARK) -> dict:
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or raw.get('version') != 1:
        raise ValueError('Versão de benchmark inválida.')
    splits = {s: [] for s in ('train','dev','test')}
    identifiers = set()
    for sample in raw.get('cases', []):
        if not isinstance(sample,dict) or sample.get('split') not in splits:
            raise ValueError('Exemplo sem divisão train/dev/test.')
        sid = str(sample.get('id', ''))
        if not re.fullmatch(r'[a-z][0-9]{2}',sid) or sid in identifiers:
            raise ValueError('IDs de exemplos têm de ser únicos.')
        identifiers.add(sid)
        for k in ('question','answer','evidence','source_id'):
            if not isinstance(sample.get(k),str) or not sample[k].strip():
                raise ValueError(f'{sid}: falta {k}')
        sources = set(re.findall(r'\[([A-Z][0-9]{2})\]',sample['evidence']))
        if sample['source_id'] not in sources or len(sources) < 2:
            raise ValueError('Cada exemplo precisa de duas fontes distintas.')
        if len(sample['question']) > 300 or len(sample['evidence']) > 2000:
            raise ValueError('Exemplo demasiado longo.')
        splits[sample['split']].append(sample)
    if any(len(v) < 3 for v in splits.values()):
        raise ValueError('Cada split deve ter pelo menos 3 exemplos.')
    return splits


class OptimizationLab:
    """DB audit + gated candidate artifacts; never modifies live LLM by itself."""
    def __init__(self, settings: Settings, db):
        self.settings, self.db = settings, db
        self.folder = settings.data_dir / 'optimizer'

    @staticmethod
    def migrate(conn) -> None:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS optimizer_runs (
                id TEXT PRIMARY KEY, method TEXT NOT NULL, model TEXT NOT NULL,
                dataset_sha256 TEXT NOT NULL, baseline_dev REAL NOT NULL,
                candidate_dev REAL NOT NULL, baseline_test REAL NOT NULL,
                candidate_test REAL NOT NULL, eligible INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'staged', artifact_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL, approved_at TEXT,
                CHECK (state IN ('staged','active','rejected','retired'))
            );
            CREATE INDEX IF NOT EXISTS ix_optimizer_runs_created ON optimizer_runs(created_at);
        ''')

    def _artifact(self, run_id: str) -> Path:
        if not re.fullmatch(r'[a-f0-9]{12}',run_id):
            raise ValueError('Identificador inválido.')
        return self.folder / f'{run_id}.json'

    def _valid_artifact(self, row) -> bool:
        try:
            path = self._artifact(row['id'])
            if not path.is_file() or path.stat().st_size > 3_000_000:
                return False
            return hashlib.sha256(path.read_bytes()).hexdigest() == row['artifact_sha256']
        except OSError:
            return False

    def stage(self, method: str, model: str, data_hash: str,
              baseline_dev: float, candidate_dev: float, baseline_test: float,
              candidate_test: float, artifact_bytes: bytes) -> dict:
        if method not in VALID_METHODS or not model.strip():
            raise ValueError('Método/modelo inválido.')
        if not all(0 <= x <= 1 for x in (baseline_dev,candidate_dev,baseline_test,candidate_test)):
            raise ValueError('Pontuações fora de [0, 1].')
        if len(artifact_bytes) > 3_000_000:
            raise ValueError('Artefacto demasiado grande.')
        # No pickle/executable serialization. DSPy state is plain JSON.
        state=json.loads(artifact_bytes.decode('utf-8'))
        if not isinstance(state,dict):
            raise ValueError('O estado DSPy tem de ser um objeto JSON.')
        self.folder.mkdir(parents=True,exist_ok=True)
        run_id = uuid4().hex[:12]
        path = self._artifact(run_id)
        try:
            with path.open('xb') as f:
                f.write(artifact_bytes)
            # Required: candidate wins on dev and unseen test; sufficiently high
            # absolute score to avoid accepting noisy improvements on a tiny set.
            eligible = (candidate_dev > baseline_dev and
                        candidate_test >= 0.8 and
                        candidate_test - baseline_test >= 0.15)
            with self.db.connect() as conn:
                conn.execute('''INSERT INTO optimizer_runs
                   (id,method,model,dataset_sha256,baseline_dev,candidate_dev,
                    baseline_test,candidate_test,eligible,state,artifact_sha256,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(
                    run_id,method,model,data_hash,baseline_dev,candidate_dev,
                    baseline_test,candidate_test,int(eligible),'staged',
                    hashlib.sha256(artifact_bytes).hexdigest(),now()))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.get(run_id)

    def get(self, run_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM optimizer_runs WHERE id=?',(run_id,)).fetchone()
        if not row:return None
        result = dict(row)
        result['artifact_intact'] = self._valid_artifact(result)
        return result

    def status(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM optimizer_runs ORDER BY created_at DESC, rowid DESC LIMIT 10').fetchall()
            active_row = conn.execute("SELECT * FROM optimizer_runs WHERE state='active' LIMIT 1").fetchone()
        items=[]
        for row in rows:
            result=dict(row)
            result['artifact_intact']=self._valid_artifact(result)
            items.append(result)
        active=dict(active_row) if active_row else None
        if active is not None:
            active['artifact_intact']=self._valid_artifact(active)
        return {'experiments':items,'active':active, 'automatic_training':False,
                'data_policy':'Apenas benchmark público incluído; nunca conversas pessoais',
                'gate':'Melhoria nos dados de validação e teste, teste ≥ 0,8 e ganho ≥ 0,15'}

    def approve(self, run_id: str) -> bool:
        row=self.get(run_id)
        if not row or row['state'] not in ('staged','active') or not row['eligible'] or not row['artifact_intact']:
            return False
        # Require matching currently installed model and dataset. No implicit
        # promotion after model changes or alterations to held-out examples.
        if row['model'] != self.settings.ollama_model or row['dataset_sha256'] != hashlib.sha256(BENCHMARK.read_bytes()).hexdigest():
            return False
        with self.db.connect() as conn:
            conn.execute("UPDATE optimizer_runs SET state='retired' WHERE state='active' AND id!=?",(run_id,))
            conn.execute("UPDATE optimizer_runs SET state='active',approved_at=? WHERE id=?",(now(),run_id))
        return True

    def rollback(self) -> bool:
        with self.db.connect() as conn:
            changed=conn.execute("UPDATE optimizer_runs SET state='retired' WHERE state='active'").rowcount
        return bool(changed)

    def _dspy(self):
        try:
            import dspy
            return dspy
        except ImportError as exc:
            raise RuntimeError('DSPy não instalado: python -m pip install -r requirements-optimizer.txt') from exc

    def _program(self, dspy):
        # Use a stable signature string to simplify JSON-only saving/loading.
        return dspy.Predict('question, evidence -> answer, source_ids')

    def _lm(self, dspy):
        # Supported official integration. Only local loopback Ollama endpoints.
        from urllib.parse import urlparse
        from ipaddress import ip_address
        uri = urlparse(self.settings.ollama_url)
        if uri.scheme != 'http' or not uri.hostname or uri.username or uri.password:
            raise ValueError('Ollama deve usar http://127.0.0.1:11434 local.')
        try: ok = ip_address(uri.hostname).is_loopback
        except ValueError: ok = uri.hostname == 'localhost'
        if not ok: raise ValueError('Ollama remoto não é permitido para otimizar.')
        return dspy.LM('ollama_chat/' + self.settings.ollama_model,
                       api_base=self.settings.ollama_url, api_key='',
                       temperature=0, max_tokens=150, cache=False)

    def _examples(self, dspy, cases: list[dict]):
        return [dspy.Example(question=c['question'],evidence=c['evidence'],
                             answer=c['answer'],source_ids=c['source_id']).with_inputs('question','evidence') for c in cases]

    @staticmethod
    def _evaluate(program, examples) -> float:
        if not examples: raise ValueError('Conjunto de teste vazio.')
        results=[]
        for case in examples:
            try:
                pred=program(question=case.question,evidence=case.evidence)
                results.append(metric_score(case,pred))
            except Exception:
                # Failed model response is always counted as failure, not omitted.
                results.append(0.0)
        return round(statistics.mean(results),6)

    def run(self, method: str = 'labeled') -> dict:
        """Slow; invoke from CLI only. Not a server task or silent scheduled job."""
        if method not in VALID_METHODS: raise ValueError('Método inválido.')
        dspy=self._dspy()
        partitions=load_benchmark()
        lm=self._lm(dspy)
        dspy.configure(lm=lm)
        train=self._examples(dspy,partitions['train'])
        dev=self._examples(dspy,partitions['dev'])
        test=self._examples(dspy,partitions['test'])
        # Candidate selection uses dev, unseen test used only after selection.
        baseline=self._program(dspy)
        baseline_dev=self._evaluate(baseline,dev)
        if method=='labeled':
            candidate=dspy.LabeledFewShot(k=min(4,len(train))).compile(
                student=self._program(dspy),trainset=train,sample=False)
        else:
            candidate=dspy.BootstrapFewShot(
                metric=metric_score,metric_threshold=1.0,
                max_bootstrapped_demos=2,max_labeled_demos=3,
                max_rounds=1,max_errors=3).compile(
                    student=self._program(dspy),trainset=train)
        candidate_dev=self._evaluate(candidate,dev)
        # Evaluate final held-out test even if dev does not improve: useful
        # audit. It must NEVER feed the optimizer's training loop.
        baseline_test=self._evaluate(baseline,test)
        candidate_test=self._evaluate(candidate,test)
        self.folder.mkdir(parents=True,exist_ok=True)
        temp=self.folder / f'.candidate-{uuid4().hex}.json'
        try:
            candidate.save(str(temp),save_program=False)
            artifact=temp.read_bytes()
        finally:
            temp.unlink(missing_ok=True)
        return self.stage(method,self.settings.ollama_model,
                          hashlib.sha256(BENCHMARK.read_bytes()).hexdigest(),
                          baseline_dev,candidate_dev,baseline_test,candidate_test,artifact)

    def answer(self, question: str, documents: list[dict]) -> dict:
        """Only use an explicitly approved DSPy candidate with checked citations."""
        with self.db.connect() as conn:
            row=conn.execute("SELECT * FROM optimizer_runs WHERE state='active' LIMIT 1").fetchone()
        if not row or not self._valid_artifact(row):
            return {'ok':False,'text':'Ainda não há uma estratégia aprovada e íntegra.'}
        if row['model'] != self.settings.ollama_model:
            return {'ok':False,'text':'O modelo mudou; a estratégia precisa de nova avaliação.'}
        if not documents:
            return {'ok':False,'text':'Não tenho fontes guardadas sobre este assunto. Pede primeiro uma investigação.'}
        # Only first 4 stored excerpts, all with grounded IDs; no source output
        # accepted except the identifiers in this snapshot.
        mapping={f'D{i:02d}':d for i,d in enumerate(documents[:4],1)}
        evidence='\n'.join(f'[{key}] {str(d.get("title",""))[:100]}: {str(d.get("content",""))[:950]}'
                           for key,d in mapping.items())
        dspy=self._dspy()
        dspy.configure(lm=self._lm(dspy))
        p=self._program(dspy)
        p.load(str(self._artifact(row['id'])))
        result=p(question=question[:350],evidence=evidence)
        cited=evidence_tokens(getattr(result,'source_ids',''))
        if not cited or cited-mapping.keys():
            return {'ok':False,'text':'Não consegui verificar as referências da resposta. Não a vou apresentar como fundamentada.'}
        answer=str(getattr(result,'answer','')).strip()[:1100]
        if not answer:
            return {'ok':False,'text':'O modelo não forneceu resposta.'}
        return {'ok':True,'text':answer+'\nFontes consultadas (não verificadas independentemente): '+
                '; '.join(str(mapping[id].get('url',''))[:220] for id in sorted(cited)),
                'sources':[{'id':id,'url':mapping[id].get('url','')} for id in sorted(cited)]}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Laboratório DSPy AURA 3.0 (local, opt-in)')
    parser.add_argument('action',choices=['status','train','approve','rollback'])
    parser.add_argument('run_id',nargs='?',default='')
    parser.add_argument('--method',choices=sorted(VALID_METHODS),default='labeled')
    args=parser.parse_args(argv)
    # CLI must never open unencrypted vault automatically.
    from .config import load_dotenv
    load_dotenv()
    from .database import Database
    from getpass import getpass
    settings=Settings.from_env()
    key=settings.database_passphrase or getpass('Frase-passe SQLCipher: ')
    if len(key)<12: raise SystemExit('Chave inválida; operação cancelada.')
    db=Database(settings.data_dir/'aura.sqlite3',passphrase=key,require_encryption=True)
    lab=OptimizationLab(settings,db)
    try:
        if args.action=='status': result=lab.status()
        elif args.action=='train': result=lab.run(args.method)
        elif args.action=='approve': result={'approved':lab.approve(args.run_id)}
        else: result={'rolled_back':lab.rollback()}
    except (RuntimeError, ValueError, OSError) as exc:
        print('Falha controlada:',str(exc),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
