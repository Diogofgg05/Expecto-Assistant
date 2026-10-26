"""AURA Book Learning 3.4: local, permission-gated, page-grounded PDF RAG.
No OCR, remote requests, automatic network downloads, or automatic promotion to truth.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from uuid import uuid4
from .database import now

class BookLearningEngine:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def migrate(db):
        db.executescript("""
          CREATE TABLE IF NOT EXISTS book_documents (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE, pages INTEGER NOT NULL, imported_at TEXT NOT NULL,
            rights_note TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS book_passages (
            id TEXT PRIMARY KEY, book_id TEXT NOT NULL, page INTEGER NOT NULL,
            ordinal INTEGER NOT NULL, text TEXT NOT NULL, text_hash TEXT NOT NULL,
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE
          );
          CREATE INDEX IF NOT EXISTS ix_book_passages_book_page ON book_passages(book_id,page);
          CREATE TABLE IF NOT EXISTS book_claims (
            id TEXT PRIMARY KEY, passage_id TEXT NOT NULL, statement TEXT NOT NULL,
            quote TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unverified_proposal',
            created_at TEXT NOT NULL,
            FOREIGN KEY(passage_id) REFERENCES book_passages(id) ON DELETE CASCADE
          );
        """)
        db.executescript("""
          CREATE TABLE IF NOT EXISTS book_chapters (
            id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_no INTEGER NOT NULL,
            title TEXT NOT NULL, start_page INTEGER NOT NULL, end_page INTEGER NOT NULL,
            method TEXT NOT NULL, UNIQUE(book_id,chapter_no),
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE
          );
          CREATE TABLE IF NOT EXISTS book_study_notes (
            id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
            note_type TEXT NOT NULL, body TEXT NOT NULL, citation_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'extractive_unverified', created_at TEXT NOT NULL,
            UNIQUE(chapter_id,note_type),
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chapter_id) REFERENCES book_chapters(id) ON DELETE CASCADE
          );
          CREATE TABLE IF NOT EXISTS book_concepts (
            id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
            term TEXT NOT NULL, normalized_term TEXT NOT NULL, page INTEGER NOT NULL,
            passage_id TEXT NOT NULL, UNIQUE(chapter_id,normalized_term),
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chapter_id) REFERENCES book_chapters(id) ON DELETE CASCADE,
            FOREIGN KEY(passage_id) REFERENCES book_passages(id) ON DELETE CASCADE
          );
          CREATE INDEX IF NOT EXISTS ix_book_concept_normalized ON book_concepts(normalized_term);
        """)
        try:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS book_passages_fts USING fts5(text, content='book_passages', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2')")
            db.executescript("""
              CREATE TRIGGER IF NOT EXISTS bp_ai AFTER INSERT ON book_passages BEGIN
                INSERT INTO book_passages_fts(rowid,text) VALUES(new.rowid,new.text); END;
              CREATE TRIGGER IF NOT EXISTS bp_ad AFTER DELETE ON book_passages BEGIN
                INSERT INTO book_passages_fts(book_passages_fts,rowid,text) VALUES('delete',old.rowid,old.text); END;
            """)
            count = db.execute('SELECT count(*) FROM book_passages').fetchone()[0]
            indexed = db.execute('SELECT count(*) FROM book_passages_fts').fetchone()[0]
            if indexed != count:
                db.execute("INSERT INTO book_passages_fts(book_passages_fts) VALUES('rebuild')")
        except Exception:
            pass  # fallback search uses SQL LIKE

    @staticmethod
    def chunks(text, max_chars=1100, overlap=140):
        text = re.sub(r'\s+', ' ', text).strip()
        if not text: return []
        result=[]; pos=0
        while pos < len(text):
            end=min(len(text), pos+max_chars)
            if end < len(text):
                split=text.rfind(' ',pos+max_chars//2,end)
                if split>pos: end=split
            part=text[pos:end].strip()
            if part: result.append(part)
            if end>=len(text):break
            pos=max(pos+1,end-overlap)
        return result

    def import_pdf(self, path, *, rights_confirmed=False, rights_note='', max_mb=40, max_pages=1500, parser='pymupdf'):
        if not rights_confirmed or not rights_note.strip():
            raise PermissionError('Confirma autorização de utilização local e regista a licença/origem.')
        p=Path(path).resolve()
        if not p.is_file() or p.suffix.lower()!='.pdf': raise ValueError('É necessário um PDF local válido.')
        if p.stat().st_size>max_mb*1024*1024: raise ValueError('PDF excede o limite de tamanho.')
        import fitz
        datahash=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.db.connect() as db:
            exists=db.execute('SELECT id FROM book_documents WHERE sha256=?',(datahash,)).fetchone()
            if exists:return {'book_id':exists['id'],'duplicate':True}
        if parser not in ('pymupdf', 'docling', 'auto'):
            raise ValueError('Parser inválido. Escolhe pymupdf, docling ou auto.')
        with fitz.open(p) as doc:
            if doc.needs_pass: raise ValueError('PDF protegido por palavra-passe.')
            if len(doc)>max_pages: raise ValueError('PDF excede o limite de páginas.')
            pages=len(doc)
            basic={i+1:page.get_text('text',sort=True) for i,page in enumerate(doc)}
        diagnostics={'parser':'pymupdf','pages_with_content':sum(bool(v.strip()) for v in basic.values())}
        page_text=basic
        if parser in ('docling','auto'):
            try:
                from .book_docling import extract_docling_pages
                structured, diagnostics = extract_docling_pages(p, pages)
                page_text=structured
            except (RuntimeError, ValueError) as exc:
                if parser=='docling': raise
                diagnostics={'parser':'pymupdf','fallback_reason':str(exc),
                             'pages_with_content':sum(bool(v.strip()) for v in basic.values())}
            # Other Docling failures must surface rather than silently corrupt results.
        entries=[]
        for number,text in sorted(page_text.items()):
            for ordinal,chunk in enumerate(self.chunks(text)):
                entries.append((uuid4().hex,number,ordinal,chunk,hashlib.sha256(chunk.encode()).hexdigest()))
        if not entries: raise ValueError('PDF sem texto extraível. PDFs digitalizados precisam de OCR autorizado.')
        bookid=uuid4().hex
        with self.db.connect() as db:
            db.execute('INSERT INTO book_documents VALUES(?,?,?,?,?,?,?)',(bookid,p.stem,p.name,datahash,pages,now(),rights_note.strip()))
            db.executemany('INSERT INTO book_passages VALUES(?,?,?,?,?,?)',[(row[0],bookid,*row[1:]) for row in entries])
        return {'book_id':bookid,'pages':pages,'passages':len(entries),'duplicate':False,'extraction':diagnostics}

    def books(self):
        with self.db.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM book_documents ORDER BY imported_at DESC')]

    def search(self, question, limit=6):
        tokens=[x for x in re.findall(r'\w+',question.casefold()) if len(x)>=3][:12]
        if not tokens:return []
        with self.db.connect() as db:
            # FTS ranking preferred; fallback uses per-token scores without trusting LLM output.
            try:
                query=' OR '.join('"'+t.replace('"','')+'"' for t in tokens)
                rows=db.execute("""SELECT p.*,b.title,b.sha256 AS book_hash,
                  bm25(book_passages_fts) AS rank FROM book_passages_fts
                  JOIN book_passages p ON p.rowid=book_passages_fts.rowid
                  JOIN book_documents b ON b.id=p.book_id
                  WHERE book_passages_fts MATCH ? ORDER BY rank LIMIT ?""",(query,limit)).fetchall()
            except Exception:
                rows=db.execute("""SELECT p.*,b.title,b.sha256 AS book_hash FROM book_passages p
                  JOIN book_documents b ON b.id=p.book_id LIMIT 10000""").fetchall()
                rows=sorted((r for r in rows if any(t in r['text'].casefold() for t in tokens)),
                            key=lambda r:-sum(r['text'].casefold().count(t) for t in tokens))[:limit]
            return [{'passage_id':r['id'],'book_id':r['book_id'],'title':r['title'],
                     'page':r['page'],'quote':r['text'],'sha256':r['text_hash']} for r in rows]

    def propose(self, passage_id, statement, exact_quote):
        statement=statement.strip(); quote=exact_quote.strip()
        if not statement or len(statement)>500 or len(quote)<12: raise ValueError('Proposta inválida.')
        with self.db.connect() as db:
            p=db.execute('SELECT text FROM book_passages WHERE id=?',(passage_id,)).fetchone()
            if not p or ' '.join(quote.split()).casefold() not in ' '.join(p['text'].split()).casefold():
                raise ValueError('A citação não consta da passagem original.')
            # Guarantee evidence exists, not logical entailment or truth.
            ident=uuid4().hex
            db.execute('INSERT INTO book_claims VALUES(?,?,?,?,?,?)',(ident,passage_id,statement,quote,'unverified_proposal',now()))
            return {'id':ident,'status':'unverified_proposal','note':'Citação confirmada, verdade não comprovada.'}

    def delete_book(self, book_id):
        with self.db.connect() as db:
            cur=db.execute('DELETE FROM book_documents WHERE id=?',(book_id,))
            return cur.rowcount
