"""Chapter study, evidence validation and educational map orchestration."""
from __future__ import annotations
from uuid import uuid4
from ..database import now
from .evidence import _quote_valid, _plausible


class BookReasoningStudyMixin:
    @staticmethod
    def _batched(passages, max_chars=4600):
        group = []
        length = 0
        for passage in passages:
            cost = len(passage['text'])
            if group and length + cost > max_chars:
                yield group
                group, length = [], 0
            group.append(passage)
            length += cost
        if group:
            yield group

    @staticmethod
    def _validate_items(payload, local, source_type):
        valid = []
        rejected = 0
        fields = {'claims': ('statement', 'claim'), 'concepts': ('definition', 'concept'),
                  'questions': ('expected_answer', 'question')}
        for section, (field, kind) in fields.items():
            raw = payload.get(section, [])
            if not isinstance(raw, list):
                rejected += 1
                continue
            for obj in raw[:12]:
                if not isinstance(obj, dict):
                    rejected += 1; continue
                pid = obj.get('passage_id')
                quote = obj.get('quote')
                statement = obj.get(field)
                if (not isinstance(pid, str) or pid not in local
                    or not isinstance(statement, str) or not 15 <= len(statement) <= 600
                    or not _quote_valid(local[pid], quote) or not _plausible(statement, quote)):
                    rejected += 1
                    continue
                if kind == 'concept':
                    name = obj.get('name')
                    if not isinstance(name, str) or not 2 <= len(name) <= 90:
                        rejected += 1; continue
                if kind == 'question':
                    question = obj.get('question')
                    if not isinstance(question, str) or not 12 <= len(question) <= 250:
                        rejected += 1; continue
                objcopy = {'kind':kind, 'body':statement, 'passage_id':pid,
                           'quote':quote, 'page':local[pid]['page']}
                if kind == 'concept':objcopy['name']=name
                if kind == 'question':objcopy['question']=question
                valid.append(objcopy)
        return valid,rejected

    async def study_chapter(self, chapter_id: str, model, *, max_batches: int = 250) -> dict:
        chapter, passages = self._chapter(chapter_id)
        batches=list(self._batched(passages))
        if len(batches)>max_batches:
            raise ValueError('Capítulo demasiado grande para o limite de estudo; aumenta max_batches.')
        run_id = uuid4().hex
        with self.db.connect() as conn:
            conn.execute('INSERT INTO book_reasoning_runs(id,book_id,chapter_id,model,status,started_at) VALUES(?,?,?,?,?,?)',
                         (run_id,chapter['book_id'],chapter_id,getattr(model,'model','test_provider'),'running',now()))
        accepted=[]; rejected=0; seen_pages=set()
        try:
            for batch in batches:
                source={p['id']:p for p in batch}
                payload={'chapter':chapter['title'],'passages':[
                    {'passage_id':p['id'],'page':p['page'],'text':p['text']} for p in batch]}
                candidate=await model.generate('extract',payload)
                if not isinstance(candidate,dict):
                    raise ValueError('O modelo não devolveu um objeto JSON')
                checked,nreject=self._validate_items(candidate,source,'extract')
                rejected+=nreject
                seen_pages.update(p['page'] for p in batch)
                accepted.extend(checked)
            if not accepted:
                raise ValueError('O motor não encontrou quaisquer propostas com citações verificáveis')
            # Summaries are synthesized only from previously validated, traceable source quotes.
            # Limit synthesis payload: useful even on large books, but report that it can be partial.
            summarized_evidence=[]
            for i,item in enumerate(accepted):
                summarized_evidence.append({'id':str(i),'kind':item['kind'],
                    'body':item['body'][:430],'page':item['page'],'quote':item['quote'][:450]})
            results=[]
            # Process in groups to avoid silently discarding late chapters.
            for start in range(0,len(summarized_evidence),12):
                chunk=summarized_evidence[start:start+12]
                synthesis=await model.generate('synthesize',{'chapter':chapter['title'],'evidence':chunk})
                valid_ids={r['id'] for r in chunk}
                points=synthesis.get('key_points',[]) if isinstance(synthesis,dict) else []
                if not isinstance(points,list):
                    rejected+=1;continue
                for point in points[:12]:
                    if not isinstance(point,dict):
                        rejected+=1;continue
                    ids=point.get('evidence_ids');body=point.get('text')
                    if (not isinstance(body,str) or not 20<=len(body)<=750
                        or not isinstance(ids,list) or not ids or len(ids)>8
                        or not all(isinstance(i,str) and i in valid_ids for i in ids)):
                        rejected+=1;continue
                    sources=[accepted[int(i)] for i in ids]
                    if not _plausible(body, ' '.join(i['quote'] for i in sources)):
                        rejected+=1;continue
                    results.append((body,sources))
            if not results:
                raise ValueError('Síntese sem referências a evidências válidas')
            with self.db.connect() as conn:
                for item in accepted:
                    evidence=[{'passage_id':item['passage_id'],'page':item['page'],'quote':item['quote']}]
                    body=(item['name']+': '+item['body'] if item['kind']=='concept' else
                          item['question']+' → '+item['body'] if item['kind']=='question' else item['body'])
                    self._save_item(conn,run_id,item['kind'],body,evidence)
                for body,items in results:
                    evidence=[{'passage_id':i['passage_id'],'page':i['page'],'quote':i['quote']} for i in items]
                    self._save_item(conn,run_id,'synthesis',body,evidence,'model_synthesis_needs_review')
                conn.execute('''UPDATE book_reasoning_runs SET status=?,finished_at=?,coverage_pages=?,available_pages=?,rejected=? WHERE id=?''',
                     ('completed',now(),len(seen_pages),len({x['page'] for x in passages}),rejected,run_id))
            return self.report(run_id)
        except Exception:
            with self.db.connect() as conn:
                conn.execute('UPDATE book_reasoning_runs SET status=?,finished_at=?,rejected=? WHERE id=?',
                             ('failed',now(),rejected,run_id))
            raise

    async def build_learning_map(self, run_id: str, model, *, max_evidence=70):
        """Second-pass relational learning on documented hypotheses.

        This creates candidate conceptual links, misconceptions and application
        exercises, not automatically certified facts or grades.
        """
        report=self.report(run_id)
        if report['status']!='completed':
            raise ValueError('Termina primeiro o estudo do capítulo')
        raw=[i for i in report['items'] if i['item_type'] in ('claim','concept','synthesis')]
        if not raw:
            raise ValueError('Não há evidências para criar relações')
        if len(raw)>max_evidence:
            raise ValueError('Mapa demasiado grande: divide o estudo em unidades menores')
        evidence=[]
        for item in raw:
            for citation in item['evidence'][:3]:
                evidence.append({'id':item['id'],'text':item['body'][:450],
                                 'passage_id':citation['passage_id'],
                                 'page':citation['page'],'quote':citation['quote'][:500]})
        response=await model.generate('map',{'chapter_id':report['chapter_id'],
                                             'evidence':evidence[:max_evidence*3]})
        if not isinstance(response,dict):
            raise ValueError('Mapa do modelo inválido')
        by_id={i['id']:i for i in raw}
        new_items=[];rejected=0
        for section,kind,body_field in (
            ('relations','concept_link','statement'),
            ('misconceptions','misconception','correction'),
            ('transfer_questions','transfer_question','rubric')):
            candidates=response.get(section,[])
            if not isinstance(candidates,list):
                rejected+=1;continue
            for candidate in candidates[:15]:
                if not isinstance(candidate,dict):
                    rejected+=1;continue
                ids=candidate.get('evidence_ids');body=candidate.get(body_field)
                if (not isinstance(ids,list) or not 1<=len(ids)<=5 or
                    any(not isinstance(i,str) or i not in by_id for i in ids) or
                    not isinstance(body,str) or not 20<=len(body)<=700):
                    rejected+=1;continue
                citations=[c for i in ids for c in by_id[i]['evidence']]
                unique={(c['passage_id'],c['page']):c for c in citations}
                if kind=='concept_link' and len(unique)<2:
                    rejected+=1;continue
                if not _plausible(body,' '.join(c['quote'] for c in unique.values())):
                    rejected+=1;continue
                if kind=='misconception':
                    mistake=candidate.get('mistake')
                    if not isinstance(mistake,str) or not 10<=len(mistake)<=350:
                        rejected+=1;continue
                    body='Erro comum: '+mistake+' | Correção proposta: '+body
                if kind=='transfer_question':
                    question=candidate.get('question')
                    if not isinstance(question,str) or not 18<=len(question)<=350:
                        rejected+=1;continue
                    body='Exercício: '+question+' | Critérios de correção: '+body
                new_items.append((kind,body,list(unique.values())))
        with self.db.connect() as conn:
            # deterministic replacement: multiple requests do not duplicate maps
            conn.execute('DELETE FROM book_reasoning_items WHERE run_id=? AND item_type IN '
                         "('concept_link','misconception','transfer_question')",(run_id,))
            for kind,body,citations in new_items:
                self._save_item(conn,run_id,kind,body,citations,'model_generated_requires_review')
            conn.execute('UPDATE book_reasoning_runs SET rejected=rejected+? WHERE id=?',(rejected,run_id))
        return {'run_id':run_id,'items':len(new_items),'rejected':rejected,
                'learning_map':self.report(run_id),
                'note':'Relações e exercícios baseados em fontes; respostas devem ser avaliadas externamente.'}
