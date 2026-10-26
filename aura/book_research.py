"""Multi-query, cross-book evidence discovery (4.1).

Evidence discovery is not proof: every result keeps an auditable passage ID and
source hash. Diversification does not manufacture consensus or factual certainty.
"""
from __future__ import annotations

import re
import hashlib
from collections import defaultdict
from .book_semantics import BookSemanticIndex, _words


class BookResearchEngine:
    def __init__(self, db):
        self.db = db
        self.index = BookSemanticIndex(db)

    async def investigate(self, questions: list[str], *, encoder=None, book_id=None,
                          limit=10, per_question=12, max_per_book=5):
        if (not isinstance(questions, list) or not 1 <= len(questions) <= 6 or
            any(not isinstance(q, str) or not 3 <= len(q.strip()) <= 800 for q in questions)):
            raise ValueError('De 1 a 6 perguntas válidas são necessárias')
        if not 1 <= limit <= 20 or not 1 <= per_question <= 20 or not 1 <= max_per_book <= 20:
            raise ValueError('Limites inválidos')
        merged = {}
        for i, question in enumerate(questions):
            results = await self.index.search(question, encoder=encoder,book_id=book_id,limit=per_question)
            for rank, passage in enumerate(results):
                pid = passage['passage_id']
                if not pid:
                    continue
                if pid not in merged:
                    merged[pid] = {**passage, 'queries_matched': [], 'fusion_score': 0.0}
                merged[pid]['fusion_score'] += 1/(60+rank+1)
                merged[pid]['queries_matched'].append(i+1)
        ranked = sorted(merged.values(),key=lambda p:(-p['fusion_score'],-len(p['queries_matched']),p['book_id'],p['page'],p['passage_id']))
        selected=[]
        book_counts=defaultdict(int)
        for passage in ranked:
            if book_counts[passage['book_id']] >= max_per_book:
                continue
            # Deduplicate highly overlapping excerpts from the same book, even across pages.
            tokens = _words(passage['text'])
            if any(passage['book_id']==chosen['book_id'] and len(tokens & _words(chosen['text'])) / max(1, min(len(tokens), len(_words(chosen['text'])))) >= .88
                   for chosen in selected):
                continue
            selected.append(passage)
            book_counts[passage['book_id']]+=1
            if len(selected)==limit:
                break
        # Double-check provenance after retrieval, so stale/corrupted passages cannot be claimed as evidence.
        verified=[]
        with self.db.connect() as conn:
            for passage in selected:
                original=conn.execute('SELECT book_id,page,text,text_hash FROM book_passages WHERE id=?',(passage['passage_id'],)).fetchone()
                if not original or original['book_id'] != passage['book_id'] or original['page'] != passage['page'] or original['text'] != passage['text'] or original['text_hash'] != passage['text_hash']:
                    continue
                verified.append({k:v for k,v in passage.items() if k!='score'} | {'fusion_score':round(passage['fusion_score'],7), 'verified_against_index':True})
        coverage={}
        for p in verified:
            coverage.setdefault(p['book_id'],{'title':p['title'],'pages':set(),'passages':0})
            coverage[p['book_id']]['pages'].add(p['page'])
            coverage[p['book_id']]['passages']+=1
        return {
            'questions':questions,
            'evidence':verified,
            'coverage':{k:{**v,'pages':sorted(v['pages'])} for k,v in coverage.items()},
            'queries_with_evidence':sorted({i for p in verified for i in p['queries_matched']}),
            'unanswered_query_numbers':[i for i in range(1,len(questions)+1) if not any(i in p['queries_matched'] for p in verified)],
            'assessment':'Relevância e cobertura documental, não verificação independente da verdade',
        }
