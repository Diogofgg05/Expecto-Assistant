"""AURA 3.5 Deep Book Study: reproducible, citation-grounded, extractive study.
No model-generated claim is considered verified. Chapter TOC preferred; fallback = page groups.
"""
from __future__ import annotations
import json, re, unicodedata
from collections import Counter
from uuid import uuid4
from .database import now
from .books import BookLearningEngine

STOP = set('sobre entre para como desde onde quando porque desta deste estas estes esse essa está estao serão depois tendo pelas pelos muito também todo todas outros outra and with from that this there which into their should about were have been what each those where after before'.split())

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).strip()

def sentences(s):
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+',s) if len(x.strip())>=32]

class DeepBookStudy:
    def __init__(self,db):
        self.db=db

    def chapterize(self,book_id,path=None,group_pages=12):
        import fitz
        with self.db.connect() as db:
            book=db.execute('SELECT * FROM book_documents WHERE id=?',(book_id,)).fetchone()
            if not book: raise ValueError('Livro não encontrado')
            if db.execute('SELECT count(*) FROM book_chapters WHERE book_id=?',(book_id,)).fetchone()[0]:
                return self.chapters(book_id)
        specs=[]
        if path:
            with fitz.open(path) as pdf:
                from hashlib import sha256
                if sha256(open(path,'rb').read()).hexdigest()!=book['sha256']:
                    raise ValueError('O PDF não corresponde ao livro importado')
                toc=[row for row in pdf.get_toc() if row[0]==1 and 1<=row[2]<=book['pages']]
                for i,item in enumerate(toc):
                    start=item[2]; end=(toc[i+1][2]-1 if i+1<len(toc) else book['pages'])
                    if end>=start:specs.append((item[1][:180],start,end,'toc'))
        if not specs:
            for start in range(1,book['pages']+1,group_pages):
                end=min(book['pages'],start+group_pages-1)
                specs.append((f'Unidade de leitura · páginas {start}–{end}',start,end,'page_group'))
        with self.db.connect() as db:
            for i,(title,start,end,method) in enumerate(specs,1):
                db.execute('INSERT OR IGNORE INTO book_chapters VALUES(?,?,?,?,?,?,?)',(uuid4().hex,book_id,i,title,start,end,method))
        return self.chapters(book_id)

    def chapters(self,book_id):
        with self.db.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM book_chapters WHERE book_id=? ORDER BY chapter_no',(book_id,))]

    def study(self,chapter_id,max_sentences=7,max_concepts=12):
        with self.db.connect() as db:
            c=db.execute('SELECT * FROM book_chapters WHERE id=?',(chapter_id,)).fetchone()
            if not c:raise ValueError('Capítulo inexistente')
            passages=[dict(x) for x in db.execute("""SELECT id,page,text FROM book_passages
              WHERE book_id=? AND page BETWEEN ? AND ? ORDER BY page,ordinal""",
              (c['book_id'],c['start_page'],c['end_page']))]
            if not passages:raise ValueError('Capítulo sem texto indexado')
            candidates=[]; count=Counter()
            for p in passages:
                for word in re.findall(r'[^\W\d_]{4,}',norm(p['text']),re.UNICODE):
                    if word not in STOP:count[word]+=1
                for line in sentences(p['text']):
                    candidates.append((line,p['page'],p['id']))
            # Summarization is explicitly extractive, with each sentence grounded in one passage.
            ranked=sorted(enumerate(candidates),key=lambda pair:(-sum(count[w] for w in set(re.findall(r'[^\W\d_]{4,}',norm(pair[1][0]))) if w not in STOP),pair[0]))
            chosen=sorted(ranked[:max_sentences],key=lambda x:x[0])
            citations=[{'page':item[1],'passage_id':item[2],'quote':item[0]} for _,item in chosen]
            summary=' '.join(item[0] for _,item in chosen)
            if not summary:summary='Sem frases completas suficientes para um resumo extrativo.'
            with self.db.connect() as db:
                db.execute("""INSERT INTO book_study_notes VALUES(?,?,?,?,?,?,?,?)
                  ON CONFLICT(chapter_id,note_type) DO UPDATE SET body=excluded.body,citation_json=excluded.citation_json,created_at=excluded.created_at""",
                  (uuid4().hex,c['book_id'],chapter_id,'extractive_summary',summary,json.dumps(citations,ensure_ascii=False),'extractive_unverified',now()))
                db.execute('DELETE FROM book_concepts WHERE chapter_id=?',(chapter_id,))
                concepts=[]
                for term,_ in count.most_common(100):
                    if len(concepts)>=max_concepts:break
                    source=next((p for p in passages if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',norm(p['text']))),None)
                    if not source:continue
                    db.execute('INSERT INTO book_concepts VALUES(?,?,?,?,?,?,?)',(uuid4().hex,c['book_id'],chapter_id,term,term,source['page'],source['id']))
                    concepts.append({'term':term,'page':source['page'],'passage_id':source['id']})
            return {'chapter':c['title'],'pages':[c['start_page'],c['end_page']],
                    'summary':summary,'citations':citations,'concepts':concepts,
                    'status':'extractive_unverified','note':'Resumo por extração literal; não é compreensão demonstrada nem verificação factual.'}

    def links(self,book_id=None,limit=40):
        with self.db.connect() as db:
            rows=db.execute("""SELECT a.normalized_term AS concept,a.book_id AS book_a,b.book_id AS book_b,
              a.page AS page_a,b.page AS page_b,a.passage_id AS passage_a,b.passage_id AS passage_b,
              da.title AS title_a,db.title AS title_b
              FROM book_concepts a JOIN book_concepts b ON a.normalized_term=b.normalized_term
              AND a.book_id < b.book_id
              JOIN book_documents da ON da.id=a.book_id JOIN book_documents db ON db.id=b.book_id
              WHERE (? IS NULL OR a.book_id=? OR b.book_id=?)
              GROUP BY a.normalized_term,a.book_id,b.book_id LIMIT ?""",(book_id,book_id,book_id,limit)).fetchall()
            return [dict(x) | {'status':'shared_term_not_proof_of_same_meaning'} for x in rows]

    def notes(self,book_id):
        with self.db.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM book_study_notes WHERE book_id=? ORDER BY created_at',(book_id,))]
