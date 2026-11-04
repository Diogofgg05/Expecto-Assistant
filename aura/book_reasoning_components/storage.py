"""Book reasoning persistence and reporting; no Ollama or retrieval dependency."""
from __future__ import annotations
import json
from uuid import uuid4
from ..database import now


class BookReasoningStorageMixin:
    @staticmethod
    def migrate(db):
        db.executescript('''
          CREATE TABLE IF NOT EXISTS book_reasoning_runs (
            id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
            model TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
            finished_at TEXT, coverage_pages INTEGER NOT NULL DEFAULT 0,
            available_pages INTEGER NOT NULL DEFAULT 0,
            rejected INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(book_id) REFERENCES book_documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chapter_id) REFERENCES book_chapters(id) ON DELETE CASCADE
          );
          CREATE TABLE IF NOT EXISTS book_reasoning_items (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, item_type TEXT NOT NULL,
            body TEXT NOT NULL, label TEXT NOT NULL,
            evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES book_reasoning_runs(id) ON DELETE CASCADE
          );
          CREATE INDEX IF NOT EXISTS ix_bri_run ON book_reasoning_items(run_id,item_type);
          CREATE TABLE IF NOT EXISTS book_concept_relations (
            id TEXT PRIMARY KEY, concept_a TEXT NOT NULL, concept_b TEXT NOT NULL,
            relation TEXT NOT NULL, explanation TEXT NOT NULL,
            evidence_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(concept_a, concept_b),
            FOREIGN KEY(concept_a) REFERENCES book_concepts(id) ON DELETE CASCADE,
            FOREIGN KEY(concept_b) REFERENCES book_concepts(id) ON DELETE CASCADE
          );
        ''')

    def _chapter(self, chapter_id):
        with self.db.connect() as conn:
            chapter = conn.execute('SELECT * FROM book_chapters WHERE id=?',(chapter_id,)).fetchone()
            if not chapter:
                raise ValueError('Capítulo não encontrado')
            passages = [dict(x) for x in conn.execute('''SELECT id,book_id,page,ordinal,text,text_hash
                    FROM book_passages WHERE book_id=? AND page BETWEEN ? AND ?
                    ORDER BY page,ordinal''',
                    (chapter['book_id'],chapter['start_page'],chapter['end_page']))]
        if not passages:
            raise ValueError('Capítulo sem texto importado')
        return dict(chapter), passages

    def _save_item(self, conn, run_id, kind, body, evidence, label='source_anchored_unverified'):
        ident = uuid4().hex
        conn.execute('INSERT INTO book_reasoning_items VALUES(?,?,?,?,?,?,?)',
                     (ident,run_id,kind,body,label,json.dumps(evidence,ensure_ascii=False),now()))
        return ident

    def report(self, run_id):
        with self.db.connect() as conn:
            run=conn.execute('SELECT * FROM book_reasoning_runs WHERE id=?',(run_id,)).fetchone()
            if not run:raise ValueError('Sessão não encontrada')
            items=[dict(r) for r in conn.execute('SELECT * FROM book_reasoning_items WHERE run_id=? ORDER BY rowid',(run_id,))]
        for item in items:
            item['evidence']=json.loads(item.pop('evidence_json'))
        cited_pages={e['page'] for item in items for e in item['evidence']}
        summary='\n'.join(x['body'] for x in items if x['item_type']=='synthesis')
        return dict(run)|{'items':items,'summary':summary,'cited_pages':len(cited_pages),'citation_coverage_ratio':round(len(cited_pages)/max(run['available_pages'],1),3),'note': 'Citações verificadas literalmente; sínteses e relações continuam a precisar de revisão semântica.'}
