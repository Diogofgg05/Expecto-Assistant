"""NotesMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
import sqlite3
import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import closing
from uuid import uuid4
from .db_shared import now, months_before
from .vault import cipher_operational_errors, encrypted_connection


class NotesMixin:
    def add_memory(self, content: str, category: str = 'note',
                   topic: str = '', importance: int = 3) -> dict:
        content = content.strip()[:2000]
        if not content:
            raise ValueError('A memória não pode estar vazia.')
        if category not in {'note','preference','project','fact','experience'}:
            category = 'note'
        item = {
            'id': uuid4().hex[:12], 'content': content, 'created_at': now(),
            'updated_at': now(), 'category': category, 'topic': topic.strip()[:160],
            'source': 'explicit_user', 'status': 'active',
            'importance': max(1, min(5, int(importance))),
        }
        with self.connect() as db:
            existing = db.execute('''SELECT * FROM memories WHERE status='active'
                                      AND lower(content) = lower(?) LIMIT 1''', (content,)).fetchone()
            if existing:
                return dict(existing)  # Do not create exact duplicates.
            db.execute('''INSERT INTO memories(id,content,created_at,updated_at,
                category,topic,source,status,importance) VALUES(:id,:content,:created_at,
                :updated_at,:category,:topic,:source,:status,:importance)''', item)
        return item

    def memory_count(self) -> int:
        """Count active memories without loading thousands of private notes."""
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM memories WHERE status='active'").fetchone()[0]

    def memories(self, limit=50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM memories WHERE status='active'
                ORDER BY created_at DESC, rowid DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_memory(self, id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id=? AND status='active'", (id,)).fetchone()
        return dict(row) if row else None

    def update_memory(self, id: str, content: str) -> dict | None:
        content = content.strip()[:2000]
        if not content:
            raise ValueError('A memória corrigida não pode estar vazia.')
        with self.connect() as db:
            old = db.execute("SELECT * FROM memories WHERE id=? AND status='active'", (id,)).fetchone()
            if old is None:
                return None
            db.execute('''INSERT INTO memory_revisions(revision_id,memory_id,previous_content,revised_at)
                VALUES(?,?,?,?)''', (uuid4().hex, id, old['content'], now()))
            db.execute('UPDATE memories SET content=?,updated_at=? WHERE id=?', (content, now(), id))
            db.execute('DELETE FROM memory_vectors WHERE memory_id=?', (id,))
            return dict(db.execute('SELECT * FROM memories WHERE id=?', (id,)).fetchone())

    def delete_memory(self, id: str) -> bool:
        with self.connect() as db:
            # CASCADE also removes all earlier revisions and vectors.
            deleted = db.execute('DELETE FROM memories WHERE id=?', (id,)).rowcount
        return bool(deleted)

    @staticmethod
    def _terms(query: str) -> list[str]:
        stop = {'que','para','sobre','com','das','dos','uma','uns','umas','qual',
                'como','quando','onde','aura','quero','sabes','lembras','minha',
                'minhas','meus','tenho','isto','essa','esse','aquilo','podes',
                'porque','gostava','mim','foi','estou','mais','por','favor'}
        seen, words = set(), []
        for word in re.findall(r'[^\W_]+', query.casefold(), flags=re.UNICODE):
            if len(word) >= 3 and word not in stop and word not in seen:
                words.append(word)
                seen.add(word)
        return words[:16]

    def search_memories(self, query: str, limit: int = 8) -> list[dict]:
        """FTS5 ranking + importance; safe bounded fallback without FTS5."""
        words = self._terms(query)
        if not words:
            return []
        limit = max(1, min(int(limit), 30))
        expression = ' OR '.join('"' + w.replace('"', '') + '"' for w in words)
        with self.connect() as db:
            try:
                rows = db.execute('''SELECT m.*, bm25(memory_fts) AS rank
                    FROM memory_fts JOIN memories m ON m.rowid=memory_fts.rowid
                    WHERE memory_fts MATCH ? AND m.status='active'
                    ORDER BY (bm25(memory_fts) - (m.importance - 3) * 0.8) ASC,
                             m.updated_at DESC LIMIT ?''', (expression, limit)).fetchall()
                return [dict(x) for x in rows]
            except cipher_operational_errors():
                parts = ['(lower(content) LIKE ? OR lower(topic) LIKE ?)'] * len(words)
                params = [p for w in words for p in ('%' + w + '%', '%' + w + '%')]
                rows = db.execute('''SELECT * FROM memories WHERE status='active' AND ('''
                    + ' OR '.join(parts) + ''') ORDER BY importance DESC, updated_at DESC
                    LIMIT ?''', (*params, limit)).fetchall()
                return [dict(x) for x in rows]

    def set_vector(self, id: str, model: str, vector: list[float]):
        if not vector or len(vector) > 8192:
            raise ValueError('Dimensão de embedding inválida.')
        with self.connect() as db:
            db.execute('''INSERT INTO memory_vectors(memory_id,model,vector_json,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(memory_id,model) DO UPDATE SET
                vector_json=excluded.vector_json,updated_at=excluded.updated_at''',
                (id, model, json.dumps(vector), now()))

    def vectors(self, model: str, limit: int = 10000) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT m.*, v.vector_json FROM memory_vectors v
                JOIN memories m ON v.memory_id=m.id WHERE v.model=? AND m.status='active'
                LIMIT ?''', (model, limit)).fetchall()
        return [dict(x) for x in rows]

    def has_memory_vectors(self, model: str) -> bool:
        """Avoid an embedding model call when no indexed notes exist."""
        with self.connect() as db:
            return bool(db.execute("""SELECT EXISTS(
                SELECT 1 FROM memory_vectors v JOIN memories m
                ON m.id=v.memory_id WHERE v.model=? AND m.status='active' LIMIT 1
            )""", (model,)).fetchone()[0])

    def iter_memory_vectors(self, model: str, limit: int = 2500, batch_size: int = 128):
        """Yield just the id and serialized vector in small DB batches.

        Keeps the same default SQL traversal order as vectors(), but does not
        materialize the note text and thousands of vectors at once.
        """
        limit = max(1, min(int(limit), 2500))
        batch_size = max(1, min(int(batch_size), 256))
        with self.connect() as db:
            cursor = db.execute("""SELECT m.id, v.vector_json FROM memory_vectors v
                JOIN memories m ON v.memory_id=m.id
                WHERE v.model=? AND m.status='active' LIMIT ?""", (model, limit))
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    yield (row['id'], row['vector_json'])

    def memory_rows_by_ids(self, ids: list[str]) -> list[dict]:
        """Materialize only the chosen note records in one bounded query."""
        ids = list(dict.fromkeys(ids))[:30]
        if not ids:
            return []
        placeholders = ','.join('?' for _ in ids)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM memories WHERE status='active' AND id IN ({placeholders})",
                ids).fetchall()
        lookup = {row['id']: dict(row) for row in rows}
        return [lookup[ident] for ident in ids if ident in lookup]

    def pending_embeddings(self, model: str, limit: int = 40) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT m.* FROM memories m
                LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.model=?
                WHERE m.status='active' AND v.memory_id IS NULL
                ORDER BY m.importance DESC,m.created_at DESC LIMIT ?''',
                (model, limit)).fetchall()
        return [dict(x) for x in rows]

    def export_memories(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT id,content,category,topic,source,importance,
                created_at,updated_at FROM memories WHERE status='active'
                ORDER BY created_at''').fetchall()
        return [dict(x) for x in rows]

    def backup(self, folder: Path) -> Path:
        """Consistent SQLite backup including memory and research knowledge."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ('aura_backup_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
        if self.encrypted:
            # Back up SQLCipher to another SQLCipher DB with SAME key; no plaintext snapshot.
            with self.connect() as source:
                with closing(encrypted_connection(target, self._passphrase)) as destination:
                    source.backup(destination)
            from .vault import verify_encrypted_database
            verify_encrypted_database(target, self._passphrase)
        else:
            with sqlite3.connect(self.path) as source, sqlite3.connect(target) as destination:
                source.backup(destination)
        return target
