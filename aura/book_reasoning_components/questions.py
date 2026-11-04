"""Evidence-first questions and cross-book comparison orchestration."""
from __future__ import annotations
import json
import re
from uuid import uuid4
from ..database import now
from .evidence import _quote_valid, _plausible


class BookReasoningQuestionMixin:
    async def answer(self, question: str, model, *, book_id=None, chapter_id=None, limit=7, encoder=None):
        if not question.strip() or len(question)>1500:
            raise ValueError('Pergunta inválida')
        # SQL FTS5 (and optional pre-indexed local embeddings) narrows a large
        # library before the LLM is allowed to write an answer. No full DB scan
        # or new web request is necessary for ordinary questions.
        matches=await self._semantic_index_factory(self.db).search(
            question,encoder=encoder,book_id=book_id,chapter_id=chapter_id,
            limit=min(max(limit,1),12))
        if not matches:
            return {'answer':None,'abstained':True,'citations':[],
                    'reason':'Nenhuma passagem relevante encontrada'}
        best=[dict(p,id=p['passage_id']) for p in matches]
        payload={'question':question,'passages':[
            {'passage_id':p['id'],'title':p['title'],'page':p['page'],'text':p['text']} for p in best]}
        response=await model.generate('answer',payload)
        if not isinstance(response,dict):raise ValueError('Resposta do modelo inválida')
        answer=response.get('answer');citations=response.get('citations',[])
        if response.get('abstain') or not isinstance(answer,str) or len(answer)>2500:
            return {'answer':None,'abstained':True,'citations':[],'reason':'Modelo absteve-se'}
        if not isinstance(citations,list) or not citations:
            return {'answer':None,'abstained':True,'citations':[],'reason':'Resposta sem citações'}
        indexed={p['id']:p for p in best}
        output=[]
        for c in citations[:8]:
            if not isinstance(c,dict) or c.get('passage_id') not in indexed or not _quote_valid(indexed[c['passage_id']],c.get('quote')):
                return {'answer':None,'abstained':True,'citations':[],'reason':'Citação não encontrada no documento'}
            passage=indexed[c['passage_id']]
            output.append({'passage_id':passage['id'],'book_id':passage['book_id'],
                           'title':passage['title'],'page':passage['page'],'quote':c['quote']})
        # A grounded quote is not enough to support a changed number. Reject
        # new numeric claims rather than mistaking lexical overlap for entailment.
        nums=lambda x: set(re.findall(r'(?<!\w)[+-]?\d+(?:[.,]\d+)?(?!\w)',x))
        evidence_text=' '.join(c['quote'] for c in output)
        if nums(answer)-nums(evidence_text):
            return {'answer':None,'abstained':True,'citations':[],
                    'reason':'Resposta introduz números sem apoio nas citações'}
        if not _plausible(answer, evidence_text):
            return {'answer':None,'abstained':True,'citations':[],'reason':'Resposta não corresponde lexicalmente às citações'}
        return {'answer':answer,'abstained':False,'citations':output,
                'status':'source_anchored_unverified','note':'A citação consta do livro; inferências do modelo não foram comprovadas.'}

    async def compare_books(self, book_a, book_b, model, limit=20):
        if book_a==book_b:raise ValueError('Escolhe livros diferentes')
        with self.db.connect() as conn:
            rows=conn.execute('''SELECT a.id AS id_a,b.id AS id_b,a.term,a.page AS page_a,b.page AS page_b,
                  pa.text AS text_a,pb.text AS text_b
                  FROM book_concepts a JOIN book_concepts b ON a.normalized_term=b.normalized_term
                  JOIN book_passages pa ON pa.id=a.passage_id
                  JOIN book_passages pb ON pb.id=b.passage_id
                  WHERE a.book_id=? AND b.book_id=? ORDER BY a.term LIMIT ?''',
                  (book_a,book_b,limit)).fetchall()
        output=[]
        for r in rows:
            x=dict(r)
            result=await model.generate('compare',{
                'concept':x['term'], 'book_a':{'page':x['page_a'],'text':x['text_a']},
                'book_b':{'page':x['page_b'],'text':x['text_b']}})
            relation=result.get('relation') if isinstance(result,dict) else None
            if (relation not in ('same','related','different','insufficient')
                or not _quote_valid({'text':x['text_a']},result.get('quote_a'))
                or not _quote_valid({'text':x['text_b']},result.get('quote_b'))):
                continue
            explanation=result.get('explanation','')
            if not isinstance(explanation,str) or len(explanation)>700:continue
            evidence=[{'page':x['page_a'],'quote':result['quote_a'],'concept_id':x['id_a']},
                      {'page':x['page_b'],'quote':result['quote_b'],'concept_id':x['id_b']}]
            with self.db.connect() as conn:
                conn.execute('''INSERT INTO book_concept_relations VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(concept_a,concept_b) DO UPDATE SET relation=excluded.relation,
                    explanation=excluded.explanation,evidence_json=excluded.evidence_json,
                    created_at=excluded.created_at''',
                    (uuid4().hex,x['id_a'],x['id_b'],relation,explanation,
                     json.dumps(evidence,ensure_ascii=False),'model_assessed_unverified',now()))
            output.append({'concept':x['term'],'relation':relation,'explanation':explanation,
                           'sources':evidence,'status':'model_assessed_unverified'})
        return output
