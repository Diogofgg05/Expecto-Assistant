"""Expecto 3.9 — human-curated, evidence-grounded open-book comprehension lab.

This does NOT train a model or independently prove semantic comprehension.
Expected answers and gold citations are NEVER sent to the model. Grading uses a
transparent lexical proxy plus complete gold-citation coverage. Results stay
explicitly *provisional* and can only be compared using the same held-out set.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from uuid import uuid4

from .database import now
from .book_reasoning import BookReasoningEngine

_STOP = {'que','como','quando','para','pelo','pela','pode','sao','uma','das','dos',
         'entre','sobre','com','este','esta','qual','quais','the','and','from',
         'this','that','with','what','which','into','there','they','have'}


def _normalized_words(s: str) -> list[str]:
    folded = unicodedata.normalize('NFKD', s.casefold())
    folded = ''.join(c for c in folded if not unicodedata.combining(c))
    return [s for s in re.findall(r'[^\W_]+', folded, re.UNICODE)
            if (len(s) > 2 or s.isdigit()) and s not in _STOP]


def token_f1(candidate: str, reference: str) -> float:
    """Simple, inspectable textual similarity, NOT a semantic truth metric."""
    a, b = Counter(_normalized_words(candidate)), Counter(_normalized_words(reference))
    if not a or not b:
        return 0.0
    shared = sum((a & b).values())
    if shared == 0:
        return 0.0
    return round(2 * shared / (sum(a.values()) + sum(b.values())), 4)


def _negation_matches(candidate: str, reference: str) -> bool:
    """Conservative red flag for polarity flips; not a logic prover."""
    def is_negative(text):
        folded = _normalized_words(text)
        return bool(set(folded) & {'nao', 'nunca', 'sem', 'jamais', 'not', 'never', 'without'})
    return is_negative(candidate) == is_negative(reference)


class BookMasteryLab:
    """Evaluate held-out, HUMAN-curated questions against the existing PDF QA engine."""

    def __init__(self, db):
        self.db = db
        with db.connect() as conn:
            self.migrate(conn)

    @staticmethod
    def migrate(conn):
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS book_mastery_runs (
            id TEXT PRIMARY KEY, dataset_hash TEXT NOT NULL, model TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, total INTEGER NOT NULL,
            passed INTEGER NOT NULL DEFAULT 0, evidence_recall REAL NOT NULL DEFAULT 0,
            average_token_f1 REAL NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT ''
          );
          CREATE TABLE IF NOT EXISTS book_mastery_cases (
            run_id TEXT NOT NULL, case_id TEXT NOT NULL, book_id TEXT NOT NULL,
            chapter_id TEXT, result TEXT NOT NULL, f1 REAL NOT NULL,
            evidence_recall REAL NOT NULL, abstained INTEGER NOT NULL,
            answer TEXT, reason TEXT NOT NULL, gold_snapshot TEXT NOT NULL,
            PRIMARY KEY(run_id,case_id),
            FOREIGN KEY(run_id) REFERENCES book_mastery_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chapter_id) REFERENCES book_chapters(id) ON DELETE CASCADE
          );
          CREATE INDEX IF NOT EXISTS ix_mastery_hash ON book_mastery_runs(dataset_hash);
        ''')

    def _validate(self, dataset: list[dict]) -> tuple[list[dict], str]:
        if not isinstance(dataset, list) or not 1 <= len(dataset) <= 150:
            raise ValueError('O benchmark deve conter 1 a 150 perguntas anotadas')
        prepared = []
        seen = set()
        with self.db.connect() as db:
            for index, case in enumerate(dataset):
                if not isinstance(case, dict) or case.get('curation') != 'human_reviewed':
                    raise ValueError(f'Caso {index}: exige curation=human_reviewed; não usar respostas geradas como gabarito')
                case_id = case.get('id')
                question = case.get('question')
                book_id = case.get('book_id')
                chapter_id = case.get('chapter_id')
                unanswerable = case.get('unanswerable', False)
                gold = case.get('gold_passage_ids')
                answer = case.get('expected_answer', '')
                if not isinstance(case_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{2,80}', case_id) or case_id in seen:
                    raise ValueError('IDs de casos inválidos ou duplicados')
                seen.add(case_id)
                if not isinstance(question, str) or not 12 <= len(question) <= 900:
                    raise ValueError(f'Pergunta inválida: {case_id}')
                if not isinstance(book_id, str) or not db.execute('SELECT 1 FROM book_documents WHERE id=?',(book_id,)).fetchone():
                    raise ValueError(f'Livro desconhecido: {case_id}')
                if chapter_id is not None:
                    if not isinstance(chapter_id, str) or not db.execute('SELECT 1 FROM book_chapters WHERE id=? AND book_id=?',(chapter_id,book_id)).fetchone():
                        raise ValueError(f'Capítulo não pertence ao livro: {case_id}')
                if not isinstance(unanswerable, bool) or not isinstance(gold,list) or len(gold) > 5:
                    raise ValueError(f'Evidências inválidas: {case_id}')
                if unanswerable:
                    if gold or answer:
                        raise ValueError('Perguntas sem resposta não podem ter resposta ou evidência gold')
                elif not gold or not isinstance(answer, str) or not 8 <= len(answer) <= 900:
                    raise ValueError('É obrigatória uma resposta de referência e passagens verificadas')
                if len(set(gold)) != len(gold) or any(not isinstance(v,str) for v in gold):
                    raise ValueError('IDs gold duplicados ou inválidos')
                snapshots = []
                for pid in gold:
                    p = db.execute('SELECT id,book_id,page,text_hash FROM book_passages WHERE id=?',(pid,)).fetchone()
                    if not p or p['book_id'] != book_id:
                        raise ValueError('Evidência gold não pertence ao livro')
                    if chapter_id:
                        ch = db.execute('SELECT start_page,end_page FROM book_chapters WHERE id=?',(chapter_id,)).fetchone()
                        if not ch['start_page'] <= p['page'] <= ch['end_page']:
                            raise ValueError('Evidência gold fora do capítulo')
                    actual=db.execute('SELECT text FROM book_passages WHERE id=?',(pid,)).fetchone()['text']
                    if hashlib.sha256(actual.encode('utf-8')).hexdigest()!=p['text_hash']:
                        raise ValueError('A passagem gold foi alterada sem atualizar o hash')
                    snapshots.append({'passage_id':p['id'],'page':p['page'],'text_hash':p['text_hash']})
                prepared.append({'id':case_id,'question':question,'book_id':book_id,
                                 'chapter_id':chapter_id,'unanswerable':unanswerable,
                                 'gold':gold,'snapshot':snapshots,'expected_answer':answer})
        # Integrity fingerprint of the held-out dataset, WITHOUT sending answers to the model.
        canonical=json.dumps(prepared,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        return prepared,hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    async def assess(self, dataset: list[dict], model, *, encoder=None,
                     min_f1: float = 0.65, limit: int = 9) -> dict:
        if not isinstance(min_f1,(int,float)) or not 0.4 <= min_f1 <= 1:
            raise ValueError('O limiar F1 deve estar entre 0.4 e 1')
        if not isinstance(limit,int) or not 1 <= limit <= 12:
            raise ValueError('Limite de pesquisa inválido')
        cases, digest = self._validate(dataset)  # FULL validation before any LLM call
        model_name = str(getattr(model, 'model', 'test_provider'))[:140]
        run_id = uuid4().hex
        with self.db.connect() as db:
            db.execute('INSERT INTO book_mastery_runs(id,dataset_hash,model,started_at,status,total) VALUES(?,?,?,?,?,?)',
                       (run_id,digest,model_name,now(),'running',len(cases)))
        reasoner=BookReasoningEngine(self.db)
        records=[]
        try:
            for c in cases:
                # Never pass expected_answer, gold passage IDs, or marking rubric to model.
                prediction=await reasoner.answer(c['question'],model,
                    book_id=c['book_id'],chapter_id=c['chapter_id'],limit=limit,encoder=encoder)
                abstained=bool(prediction.get('abstained'))
                found_ids={x['passage_id'] for x in prediction.get('citations',[])}
                citation_score=(len(found_ids.intersection(c['gold']))/len(c['gold'])) if c['gold'] else 0.0
                f1=token_f1(prediction.get('answer') or '',c['expected_answer']) if not abstained else 0.0
                if c['unanswerable']:
                    ok=abstained
                    result='correct_abstention' if ok else 'answered_without_reference'
                    recall=1.0 if ok else 0.0
                else:
                    polarity_ok = not abstained and _negation_matches(prediction.get('answer') or '', c['expected_answer'])
                    ok=not abstained and citation_score==1.0 and f1>=min_f1 and polarity_ok
                    result='provisional_match' if ok else ('abstained' if abstained else
                        'missed_gold_evidence' if citation_score<1 else
                        'polarity_mismatch' if not polarity_ok else 'low_text_similarity')
                    recall=citation_score
                records.append({'case_id':c['id'],'book_id':c['book_id'],
                    'chapter_id':c['chapter_id'],'result':result,'passed':ok,
                    'f1':f1,'recall':recall,'abstained':abstained,
                    'answer':prediction.get('answer'),
                    'reason':prediction.get('reason',''), 'snapshot':c['snapshot']})
            with self.db.connect() as db:
                for r in records:
                    db.execute('''INSERT INTO book_mastery_cases
                        (run_id,case_id,book_id,chapter_id,result,f1,evidence_recall,abstained,answer,reason,gold_snapshot)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                        (run_id,r['case_id'],r['book_id'],r['chapter_id'],r['result'],r['f1'],r['recall'],
                         int(r['abstained']),r['answer'],r['reason'],json.dumps(r['snapshot'])))
                db.execute('''UPDATE book_mastery_runs SET status='completed',finished_at=?,passed=?,
                    evidence_recall=?,average_token_f1=?,note=? WHERE id=?''',
                    (now(),sum(x['passed'] for x in records),round(sum(x['recall'] for x in records)/len(records),4),
                     round(sum(x['f1'] for x in records)/len(records),4),
                     'Avaliação provisória de respostas com livro aberto; não prova compreensão nem treino dos pesos.',run_id))
        except Exception:
            with self.db.connect() as db:
                db.execute('UPDATE book_mastery_runs SET status=?,finished_at=? WHERE id=?',('failed',now(),run_id))
            raise
        return self.report(run_id)

    def report(self, run_id: str) -> dict:
        with self.db.connect() as db:
            run=db.execute('SELECT * FROM book_mastery_runs WHERE id=?',(run_id,)).fetchone()
            if not run:
                raise ValueError('Avaliação desconhecida')
            rows=[dict(x) for x in db.execute('SELECT * FROM book_mastery_cases WHERE run_id=? ORDER BY rowid',(run_id,))]
            if not rows and run['status']=='completed':
                stale=True
            else:
                stale=len(rows)!=run['total']
            for row in rows:
                gold=json.loads(row.pop('gold_snapshot'))
                row['gold_pages']=sorted({x['page'] for x in gold})
                for evidence in gold:
                    latest=db.execute('SELECT text,text_hash FROM book_passages WHERE id=?',(evidence['passage_id'],)).fetchone()
                    if latest is None or latest['text_hash']!=evidence['text_hash'] or hashlib.sha256(latest['text'].encode('utf-8')).hexdigest()!=latest['text_hash']:
                        stale=True
                # IDs and reference answers intentionally not copied to stored answer output.
            result=dict(run)
        result['cases']=rows
        result['stale_sources']=stale
        result['provisional_pass_rate']=round(run['passed']/run['total'],4) if run['status']=='completed' and not stale else None
        result['gaps']=[{'case_id':x['case_id'],'book_id':x['book_id'],'chapter_id':x['chapter_id'],
                         'pages_for_review':x['gold_pages'],'reason':x['result']}
                        for x in rows if x['result'] not in ('provisional_match','correct_abstention')]
        result['interpretation']='Indicador lexical e de citações para revisão humana; não comprova aprendizagem autónoma nem equivalência semântica.'
        return result

    def history(self, dataset_hash: str | None = None, limit=20) -> list[dict]:
        with self.db.connect() as db:
            if dataset_hash:
                rows=db.execute('''SELECT id FROM book_mastery_runs WHERE dataset_hash=?
                    ORDER BY started_at DESC,id DESC LIMIT ?''',(dataset_hash,limit)).fetchall()
            else:
                rows=db.execute('''SELECT id FROM book_mastery_runs ORDER BY started_at DESC,id DESC LIMIT ?''',(limit,)).fetchall()
        return [self.report(x['id']) for x in rows]

    def remediation(self, run_id: str) -> dict:
        """Source-linked re-study plan. No answer keys enter an autonomous learning loop."""
        report = self.report(run_id)
        if report['status'] != 'completed' or report['stale_sources']:
            raise ValueError('Não é possível planear revisão sobre uma avaliação incompleta ou fontes alteradas')
        grouped = {}
        with self.db.connect() as db:
            for gap in report['gaps']:
                ch = gap['chapter_id']
                key = (gap['book_id'], ch)
                if key not in grouped:
                    chapter = db.execute('SELECT title,start_page,end_page FROM book_chapters WHERE id=?',(ch,)).fetchone() if ch else None
                    book = db.execute('SELECT title FROM book_documents WHERE id=?',(gap['book_id'],)).fetchone()
                    grouped[key]={'book_id':gap['book_id'],'book_title':book['title'] if book else '',
                                  'chapter_id':ch,'chapter_title':chapter['title'] if chapter else 'Livro completo',
                                  'missed_cases':0,'review_pages':set(),'reasons':set()}
                grouped[key]['missed_cases']+=1
                grouped[key]['review_pages'].update(gap['pages_for_review'])
                grouped[key]['reasons'].add(gap['reason'])
        proposals=[]
        for group in grouped.values():
            group['review_pages']=sorted(group['review_pages'])
            group['reasons']=sorted(group['reasons'])
            group['next_step']=('Rever as passagens indicadas e repetir o teste com novas perguntas '
                                'curadas por humanos, não treinadas nos itens originais.')
            proposals.append(group)
        proposals.sort(key=lambda item:(-item['missed_cases'], item['book_title'], item['chapter_title']))
        return {'run_id':run_id,'chapters_to_review':proposals,
                'note':'A revisão não altera pesos do modelo nem incorpora respostas gold na sua memória.'}

    def compare(self, previous_run_id: str, current_run_id: str) -> dict:
        """Compare ONLY the exact same manual benchmark; no cross-set score inflation."""
        if previous_run_id == current_run_id:
            raise ValueError('Seleciona duas avaliações diferentes')
        before, after = self.report(previous_run_id), self.report(current_run_id)
        if (before['status'] != 'completed' or after['status'] != 'completed'
                or before['stale_sources'] or after['stale_sources']):
            raise ValueError('Avaliações incompletas ou com evidências desatualizadas')
        if before['dataset_hash'] != after['dataset_hash']:
            raise ValueError('Não se podem comparar conjuntos de perguntas diferentes')
        return {'previous_id':previous_run_id, 'current_id':current_run_id,
                'delta_provisional_pass_rate':round(after['provisional_pass_rate']-before['provisional_pass_rate'],4),
                'delta_token_f1':round(after['average_token_f1']-before['average_token_f1'],4),
                'delta_evidence_recall':round(after['evidence_recall']-before['evidence_recall'],4),
                'note':'Repetir as mesmas perguntas pode gerar memorização do benchmark; validar em casos novos.'}
