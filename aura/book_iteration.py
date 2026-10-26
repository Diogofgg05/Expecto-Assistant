"""Expecto 4.0 — independent book-learning evaluation and retrieval strategy lab.

This is NOT weight training, causal proof of intelligence, nor a self-grading judge.
Training, validation and holdout are human-curated; benchmark answers are only
used by the grader. Prompt/model candidate changes are never deployed here.
"""
from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
import json
import re
import unicodedata
from collections import defaultdict
from uuid import uuid4

from .book_mastery import BookMasteryLab, _normalized_words
from .database import now


def _fingerprint(splits):
    return hashlib.sha256(json.dumps(splits, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def _clean_question(text):
    decomposed = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+', text, re.UNICODE))


def _score(report):
    """Transparent proxy: citation+answer exactness proxy; no model judges itself."""
    if report['status'] != 'completed' or report['stale_sources']:
        raise ValueError('Avaliação incompleta ou fontes alteradas')
    return round(0.7 * report['provisional_pass_rate'] +
                 0.2 * report['evidence_recall'] +
                 0.1 * report['average_token_f1'], 5)


class BookIterationLab:
    """Tune retrieval budget offline; leave default runtime and LLM untouched."""

    def __init__(self, db):
        self.db = db
        self.mastery = BookMasteryLab(db)
        with db.connect() as conn:
            self.migrate(conn)

    @staticmethod
    def migrate(conn):
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS book_iteration_runs(
          id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          status TEXT NOT NULL, dataset_hash TEXT NOT NULL,
          model TEXT NOT NULL, baseline_limit INTEGER NOT NULL,
          chosen_limit INTEGER, baseline_validation_id TEXT,
          chosen_validation_id TEXT, train_diagnostic_id TEXT,
          holdout_baseline_id TEXT, holdout_chosen_id TEXT,
          recommendation TEXT NOT NULL DEFAULT 'not_evaluated',
          trace_json TEXT NOT NULL DEFAULT '{}',
          error TEXT NOT NULL DEFAULT '',
          FOREIGN KEY(baseline_validation_id) REFERENCES book_mastery_runs(id),
          FOREIGN KEY(chosen_validation_id) REFERENCES book_mastery_runs(id),
          FOREIGN KEY(train_diagnostic_id) REFERENCES book_mastery_runs(id),
          FOREIGN KEY(holdout_baseline_id) REFERENCES book_mastery_runs(id),
          FOREIGN KEY(holdout_chosen_id) REFERENCES book_mastery_runs(id)
        );
        CREATE INDEX IF NOT EXISTS ix_iteration_time ON book_iteration_runs(started_at);
        ''')

    def _validate(self, bundle, limits):
        if not isinstance(bundle, dict) or set(bundle) != {'train', 'validation', 'holdout'}:
            raise ValueError('O benchmark precisa de train, validation e holdout independentes')
        if not isinstance(limits, (list, tuple)) or not 2 <= len(limits) <= 4:
            raise ValueError('Especifica entre 2 e 4 limites de pesquisa')
        if any(type(n) is not int or not 1 <= n <= 12 for n in limits) or len(set(limits)) != len(limits):
            raise ValueError('Limites duplicados ou fora do intervalo 1..12')
        normalized = defaultdict(list)
        ids = set()
        for split, cases in bundle.items():
            if not isinstance(cases, list) or not 2 <= len(cases) <= 25:
                raise ValueError(f'{split}: são precisas entre 2 e 25 perguntas humanas')
            # Existing validator checks provenance, passage ownership and hashes.
            self.mastery._validate(cases)
            for case in cases:
                if case['id'] in ids:
                    raise ValueError('IDs de casos não podem repetir-se entre divisões')
                ids.add(case['id'])
                q = _clean_question(case['question'])
                if len(q) < 8:
                    raise ValueError('Pergunta demasiado pequena')
                normalized[split].append(q)
        # Exact and near-duplicate questions between splits inflate the holdout.
        for left, right in (('train','validation'), ('train','holdout'), ('validation','holdout')):
            for x in normalized[left]:
                for y in normalized[right]:
                    sx, sy = set(_normalized_words(x)), set(_normalized_words(y))
                    if x == y or SequenceMatcher(None, x, y).ratio() > 0.88 or (
                        len(sx)>=5 and len(sy)>=5 and
                        len(sx & sy)/len(sx | sy) > 0.82):
                        raise ValueError('Perguntas iguais ou demasiado semelhantes entre train/validation/holdout')
        return _fingerprint(bundle)

    async def run(self, bundle, model, *, limits=(4, 8, 12), encoder=None):
        """Use train to propose, validation to select, holdout ONCE to audit.

        This may take many model calls; upper bounded by 25*4+25*2+25*2.
        Explicit user action is required to run. It NEVER updates deployment.
        """
        digest = self._validate(bundle, limits)
        chosen_baseline = limits[0]
        run_id = uuid4().hex
        name = str(getattr(model, 'model', 'test_provider'))[:140]
        with self.db.connect() as conn:
            conn.execute('''INSERT INTO book_iteration_runs
                (id,started_at,status,dataset_hash,model,baseline_limit)
                VALUES(?,?,?,?,?,?)''',
                (run_id, now(), 'running', digest, name, chosen_baseline))
        trace = {'limits':list(limits), 'train':[], 'validation':{}, 'holdout':{},
                 'decision_rule':'A estratégia não é instalada automaticamente.',
                 'benchmark_limits':'Métrica lexical+evidências; não prova compreensão.'}
        train_diag = None
        baseline_validation = None
        selected_validation = None
        holdout_baseline = None
        holdout_selected = None
        chosen = chosen_baseline
        recommendation = 'not_evaluated'
        try:
            # Train: propose retrieval candidates from the training split only.
            training = []
            for limit in limits:
                r = await self.mastery.assess(bundle['train'], model, encoder=encoder, limit=limit)
                training.append((limit, _score(r), r))
                trace['train'].append({'limit':limit,'score':_score(r),
                    'pass_rate':r['provisional_pass_rate'], 'run_id':r['id']})
            train_diag = training[0][2]['id']
            best = max(training, key=lambda x:(x[1], -limits.index(x[0])))
            chosen = best[0]
            # Validation: only the training winner and the baseline may be compared.
            baseline_validation = await self.mastery.assess(
                bundle['validation'],model,encoder=encoder,limit=chosen_baseline)
            if chosen == chosen_baseline:
                selected_validation=baseline_validation
            else:
                selected_validation=await self.mastery.assess(
                    bundle['validation'],model,encoder=encoder,limit=chosen)
            bscore, sscore = _score(baseline_validation), _score(selected_validation)
            trace['validation'] = {'baseline_score':bscore,'candidate_score':sscore,
               'baseline_run':baseline_validation['id'],'candidate_run':selected_validation['id']}
            # Holdout: used after selection only. Never to tune/select other candidates.
            holdout_baseline=await self.mastery.assess(bundle['holdout'],model,
                encoder=encoder,limit=chosen_baseline)
            if chosen == chosen_baseline:
                holdout_selected=holdout_baseline
            else:
                holdout_selected=await self.mastery.assess(bundle['holdout'],model,
                    encoder=encoder,limit=chosen)
            hbase,hchosen=_score(holdout_baseline),_score(holdout_selected)
            trace['holdout']={'baseline_score':hbase,'candidate_score':hchosen,
                'baseline_run':holdout_baseline['id'],'candidate_run':holdout_selected['id']}
            # No self-deployment. Holdout regression vetoes even a validation gain.
            if chosen == chosen_baseline:
                recommendation='no_training_gain'
            elif sscore < bscore + 0.05:
                recommendation='insufficient_validation_gain'
            elif hchosen + 1e-9 < hbase:
                recommendation='holdout_regression'
            else:
                recommendation='candidate_requires_human_approval'
            with self.db.connect() as conn:
                conn.execute('''UPDATE book_iteration_runs SET
                  finished_at=?, status='completed', chosen_limit=?,
                  baseline_validation_id=?, chosen_validation_id=?, train_diagnostic_id=?,
                  holdout_baseline_id=?,holdout_chosen_id=?,recommendation=?,trace_json=?
                  WHERE id=?''', (now(),chosen,baseline_validation['id'],
                      selected_validation['id'],train_diag,holdout_baseline['id'],
                      holdout_selected['id'],recommendation,
                      json.dumps(trace,ensure_ascii=False),run_id))
        except Exception as e:
            with self.db.connect() as conn:
                conn.execute('UPDATE book_iteration_runs SET status=?,finished_at=?,error=? WHERE id=?',
                    ('failed',now(),str(e)[:400],run_id))
            raise
        return self.report(run_id)

    def report(self, run_id):
        with self.db.connect() as conn:
            row=conn.execute('SELECT * FROM book_iteration_runs WHERE id=?',(run_id,)).fetchone()
        if row is None:
            raise ValueError('Ciclo desconhecido')
        result=dict(row)
        result['trace']=json.loads(result.pop('trace_json'))
        result['changed_production']=False
        result['weights_updated']=False
        # BookMasteryLab checks that cited gold sources have not been altered.
        for field in ('baseline_validation_id','chosen_validation_id','train_diagnostic_id',
                      'holdout_baseline_id','holdout_chosen_id'):
            if result.get(field):
                r=self.mastery.report(result[field])
                if r['stale_sources']:
                    result['recommendation']='stale_sources_do_not_apply'
                    break
        result['note']='Ciclo de avaliação com conjunto reservado. Não atualiza os pesos do modelo nem comprova inteligência geral.'
        return result

    async def restudy(self, run_id: str, model, *, max_chapters=2):
        """Explicitly re-read the chapters missed in TRAIN; no test-answer leakage.

        This stores sourced learning *proposals* in the pre-existing study engine.
        It cannot update LLM weights, runtime configuration or benchmark answers.
        """
        if type(max_chapters) is not int or not 1 <= max_chapters <= 3:
            raise ValueError('Limite de capítulos inválido')
        plan=self.review(run_id)
        from .book_reasoning import BookReasoningEngine
        engine=BookReasoningEngine(self.db)
        reviewed=[]
        for item in plan['review_chapters']:
            chapter_id=item['chapter_id']
            if not chapter_id:
                continue  # require traceable, pre-indexed chapter boundaries
            result=await engine.study_chapter(chapter_id,model,max_batches=20)
            reviewed.append({'chapter_id':chapter_id,'run_id':result['id'],
                             'coverage_pages':result['coverage_pages'],
                             'available_pages':result['available_pages'],
                             'status':result['status']})
            if len(reviewed)>=max_chapters:
                break
        return {'iteration_id':run_id,'study_runs':reviewed,
                'note':('Leitura opcional autorizada, limitada a capítulos em que o treino falhou. '
                        'Guarda hipóteses com citações, não respostas comprovadas. '
                        'Para medir melhoria usa novas perguntas reservadas.')}

    def history(self, limit=20):
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Limite inválido')
        with self.db.connect() as conn:
            run_ids=[x['id'] for x in conn.execute(
                'SELECT id FROM book_iteration_runs ORDER BY started_at DESC, id DESC LIMIT ?',
                (limit,))]
        return [self.report(x) for x in run_ids]

    def review(self, run_id: str, *, max_quotes=8):
        """Return targeted reading passages from TRAIN only; never holdout keys."""
        if not 1 <= max_quotes <= 20:
            raise ValueError('Número de citações inválido')
        summary=self.report(run_id)
        if summary['status']!='completed':
            raise ValueError('Termina primeiro o ciclo')
        train_id=summary['train_diagnostic_id']
        train=self.mastery.report(train_id)
        if train['stale_sources']:
            raise ValueError('Fontes alteradas')
        suggested=self.mastery.remediation(train_id)
        reviews=[]
        with self.db.connect() as conn:
            for chapter in suggested['chapters_to_review'][:8]:
                bid=chapter['book_id']
                pages=chapter['review_pages'][:max_quotes]
                retrieved=[]
                for page in pages:
                    rows=conn.execute('''SELECT id,page,text,text_hash FROM book_passages
                        WHERE book_id=? AND page=? ORDER BY id LIMIT 2''',(bid,page)).fetchall()
                    for r in rows:
                        if hashlib.sha256(r['text'].encode('utf-8')).hexdigest()!=r['text_hash']:
                            raise ValueError('A fonte foi alterada')
                        retrieved.append({'page':page,'passage_id':r['id'],
                                          'excerpt':r['text'][:400],
                                          'status':'reading_material_not_verified_fact'})
                reviews.append({'book_id':bid,'chapter_id':chapter['chapter_id'],
                    'chapter_title':chapter['chapter_title'], 'pages':pages,
                    'passages':retrieved[:max_quotes], 'missed_cases':chapter['missed_cases']})
        return {'run_id':run_id,'review_chapters':reviews,
                'note':'Plano baseado exclusivamente nas falhas do treino. Não expõe respostas da validação ou teste reservado.'}
