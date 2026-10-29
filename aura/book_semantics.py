"""Expecto 3.8: persistent local book embeddings + bounded hybrid retrieval.

Embedding similarity estimates *relevance*, never factual truth. Indexing is opt-in,
local, and uses existing authorized text passages only. No downloads or OCR.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from typing import Protocol

from .database import now


def _words(value: str) -> set[str]:
    value = ''.join(x for x in unicodedata.normalize('NFKD', value.casefold())
                    if unicodedata.category(x) != 'Mn')
    stop = {'para','como','quais','qual','quais','sobre','desta','deste','quando','onde',
            'porque','entre','com','dos','das','uma','uns','que','sao','por','the','and',
            'what','which','how','from','this','that','are','were'}
    return {x for x in re.findall(r'[^\W\d_]{3,}', value) if x not in stop}


def _unit(vec):
    if not isinstance(vec, (list, tuple)) or not 2 <= len(vec) <= 4096:
        raise ValueError('Embedding inválido: dimensão não suportada')
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in vec):
        raise ValueError('Embedding contém valores inválidos')
    magnitude = math.sqrt(sum(x*x for x in vec))
    if magnitude <= 1e-12:
        raise ValueError('Embedding nulo')
    return [float(x)/magnitude for x in vec]


class Encoder(Protocol):
    model: str
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaBookEncoder:
    def __init__(self, model: str = 'qwen3-embedding:0.6b', base_url: str = 'http://127.0.0.1:11434'):
        if not model.strip() or not base_url.startswith(('http://127.0.0.1:', 'http://localhost:')):
            raise ValueError('O encoder tem de usar Ollama local e um modelo definido')
        self.model, self.base_url = model, base_url.rstrip('/')

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or len(texts) > 16 or any(not x.strip() or len(x)>8000 for x in texts):
            raise ValueError('Lote de embeddings fora dos limites')
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=3.0)) as client:
            response = await client.post(self.base_url+'/api/embed',json={'model':self.model,'input':texts})
            response.raise_for_status()
            result = response.json().get('embeddings')
        if not isinstance(result,list) or len(result)!=len(texts):
            raise ValueError('Resposta de embeddings incompleta')
        return result


class BookSemanticIndex:
    def __init__(self, db):
        self.db = db
        with db.connect() as conn:
            self.migrate(conn)

    @staticmethod
    def migrate(db):
        db.executescript('''
          CREATE TABLE IF NOT EXISTS book_embeddings (
            passage_id TEXT NOT NULL, model TEXT NOT NULL, text_hash TEXT NOT NULL,
            dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL, indexed_at TEXT NOT NULL,
            PRIMARY KEY (passage_id,model),
            FOREIGN KEY(passage_id) REFERENCES book_passages(id) ON DELETE CASCADE
          );
          CREATE INDEX IF NOT EXISTS ix_book_embeddings_model ON book_embeddings(model);
        ''')

    async def index_book(self, book_id: str, encoder: Encoder, *, batch_size=12, max_passages=15000):
        if not 1 <= batch_size <= 16 or not 1 <= max_passages <= 50000:
            raise ValueError('Limites de indexação inválidos')
        with self.db.connect() as conn:
            if not conn.execute('SELECT 1 FROM book_documents WHERE id=?',(book_id,)).fetchone():
                raise ValueError('Livro inexistente')
            rows=[dict(row) for row in conn.execute('''SELECT p.id,p.text,p.text_hash,e.text_hash AS old_hash
                FROM book_passages p LEFT JOIN book_embeddings e ON e.passage_id=p.id AND e.model=?
                WHERE p.book_id=? ORDER BY p.page,p.ordinal''',(encoder.model,book_id))]
        if len(rows)>max_passages:
            raise ValueError('Livro excede o limite explícito de indexação')
        queue = [r for r in rows if r['text_hash']!=r['old_hash']]
        indexed = 0
        for offset in range(0,len(queue),batch_size):
            batch=queue[offset:offset+batch_size]
            normalized=[_unit(v) for v in await encoder.embed([r['text'] for r in batch])]
            if len(normalized)!=len(batch) or len({len(v) for v in normalized})!=1:
                raise ValueError('Embeddings com dimensões incompatíveis')
            with self.db.connect() as conn:
                for r,vector in zip(batch,normalized):
                    # An indexed passage must still have the source hash we read.
                    conn.execute('''INSERT INTO book_embeddings VALUES(?,?,?,?,?,?)
                       ON CONFLICT(passage_id,model) DO UPDATE SET
                       text_hash=excluded.text_hash,dimensions=excluded.dimensions,
                       vector_json=excluded.vector_json,indexed_at=excluded.indexed_at''',
                       (r['id'],encoder.model,r['text_hash'],len(vector),json.dumps(vector),now()))
                    indexed+=1
        return {'book_id':book_id,'model':encoder.model,'indexed':indexed,'reused':len(rows)-len(queue),
                'total':len(rows),'note':'Vetores de relevância, não certificados de verdade'}

    async def search(self, question: str, *, encoder: Encoder|None=None,
                     book_id: str|None=None, chapter_id: str|None=None,
                     limit: int=7, candidate_limit: int=300):
        if not isinstance(question,str) or not 3 <= len(question.strip()) <= 1500:
            raise ValueError('Pergunta inválida')
        if not 1 <= limit <= 20 or not 50 <= candidate_limit <= 10000:
            raise ValueError('Limites de pesquisa inválidos')
        filters=[]; params=[]
        if book_id:
            filters.append('p.book_id=?');params.append(book_id)
        if chapter_id:
            with self.db.connect() as conn:
                c=conn.execute('SELECT book_id,start_page,end_page FROM book_chapters WHERE id=?',(chapter_id,)).fetchone()
            if not c or (book_id and c['book_id']!=book_id):
                raise ValueError('Capítulo ou livro incompatível')
            filters += ['p.book_id=?','p.page BETWEEN ? AND ?'];params += [c['book_id'],c['start_page'],c['end_page']]
        where=(' AND '+' AND '.join(filters)) if filters else ''
        words=_words(question)
        scores=defaultdict(float)
        passages={}
        with self.db.connect() as conn:
            if words:
                try:
                    query=' OR '.join('"'+w+'"' for w in sorted(words)[:16])
                    lex=[dict(x) for x in conn.execute('''SELECT p.id,p.book_id,p.page,p.ordinal,p.text,p.text_hash,b.title
                        FROM book_passages_fts f JOIN book_passages p ON p.rowid=f.rowid
                        JOIN book_documents b ON b.id=p.book_id
                        WHERE book_passages_fts MATCH ?'''+where+'''
                        ORDER BY bm25(book_passages_fts) LIMIT ?''',
                        [query,*params,candidate_limit]).fetchall()]
                except Exception:
                    # Fallback only when SQLite FTS5 is unavailable; an empty
                    # *valid* FTS result must not silently scan just early pages.
                    lex=[dict(x) for x in conn.execute('''SELECT p.id,p.book_id,p.page,p.ordinal,p.text,p.text_hash,b.title
                        FROM book_passages p JOIN book_documents b ON b.id=p.book_id
                        WHERE 1=1'''+where+' ORDER BY p.page,p.ordinal LIMIT ?',
                        [*params,candidate_limit]).fetchall()]
                    lex.sort(key=lambda p:-len(words & _words(p['text'])))
                    lex=[p for p in lex if words & _words(p['text'])]
                for rank,p in enumerate(lex):
                    passages[p['id']]=p
                    # Reciprocal rank fusion: lexical evidence is independent of vector similarity.
                    scores[p['id']]+=1/(60+rank+1)
            if encoder is not None:
                # Validate a query embedding once, then search stored, matching source hashes.
                query_vector=_unit((await encoder.embed([question]))[0])
                embeddings=conn.execute('''SELECT e.passage_id,e.vector_json,e.dimensions,p.book_id,p.page,
                    p.ordinal,p.text,p.text_hash,b.title FROM book_embeddings e
                    JOIN book_passages p ON p.id=e.passage_id AND p.text_hash=e.text_hash
                    JOIN book_documents b ON b.id=p.book_id
                    WHERE e.model=? AND e.dimensions=?'''+where+' LIMIT ?',
                    [encoder.model,len(query_vector),*params,candidate_limit*30]).fetchall()
                ranked=[]
                for item in embeddings:
                    v=json.loads(item['vector_json'])
                    if len(v)!=len(query_vector):continue
                    score=sum(x*y for x,y in zip(query_vector,v))
                    if math.isfinite(score) and score>=0.37:
                        ranked.append((score,dict(item)))
                ranked.sort(key=lambda x:-x[0])
                for rank,(score,p) in enumerate(ranked[:candidate_limit]):
                    passages[p['passage_id']]=p
                    scores[p['passage_id']]+=1/(60+rank+1)
        ordered=sorted(scores,key=lambda pid:(-scores[pid], passages[pid]['page'],pid))
        chosen=[]
        for pid in ordered:
            p=passages[pid]
            # adjacent chunks overlap; suppress near duplicate results on same page.
            if any(x['book_id']==p['book_id'] and x['page']==p['page'] and
                   len(_words(x['text']) & _words(p['text']))/max(1,len(_words(p['text'])))>0.85 for x in chosen):
                continue
            chosen.append(p)
            if len(chosen)>=limit:break
        return [{'passage_id':p.get('passage_id',p['id'] if 'id' in p else None),
                 'book_id':p['book_id'],'title':p['title'],'page':p['page'],
                 'text':p['text'],'text_hash':p['text_hash'],'score':round(scores[p.get('passage_id',p.get('id'))],6)}
                for p in chosen]

    async def evaluate_retrieval(self, cases, *, encoder: Encoder|None=None, limit=5):
        """Human-labelled gold passage IDs; no LLM grades its own answers."""
        if not isinstance(cases,list) or not 1 <= len(cases)<=200:
            raise ValueError('Conjunto de avaliação inválido')
        if not isinstance(limit,int) or isinstance(limit,bool) or not 1 <= limit <= 20:
            raise ValueError('k deve estar entre 1 e 20')
        found=0;rr=0;recall_total=0.0;precision_total=0.0;details=[]
        for c in cases:
            if (not isinstance(c,dict) or not isinstance(c.get('question'),str)
                    or not c['question'].strip() or not isinstance(c.get('gold_passage_ids'),list)
                    or not c['gold_passage_ids']
                    or any(not isinstance(g,str) or not g.strip() for g in c['gold_passage_ids'])):
                raise ValueError('Cada caso precisa de pergunta e IDs esperados identificados manualmente')
            gold=set(c['gold_passage_ids'])
            matched=await self.search(c['question'],encoder=encoder,book_id=c.get('book_id'),limit=limit)
            ids=[r['passage_id'] for r in matched]
            ranks=[i+1 for i,passage_id in enumerate(ids) if passage_id in gold]
            best=min(ranks) if ranks else None
            hits=len(set(ids[:limit]) & gold)
            recall=hits/len(gold)
            precision=hits/limit
            found+=bool(best);rr+=(1/best if best else 0)
            recall_total+=recall;precision_total+=precision
            details.append({'question':c['question'],'hit':bool(best),'rank':best,
                            'gold_count':len(gold),'matched_gold':hits,
                            'recall_at_k':round(recall,3),
                            'precision_at_k':round(precision,3)})
        count=len(cases)
        return {'cases':count,'hit_at_k':round(found/count,3),
                'mrr':round(rr/count,3),'recall_at_k':round(recall_total/count,3),
                'precision_at_k':round(precision_total/count,3),
                'k':limit,'details':details,
                'note':'Mede recuperação de evidências rotuladas; não prova compreensão, inferência ou verdade'}
