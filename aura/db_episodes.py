"""EpisodesMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
import re
import json
from uuid import uuid4
from .db_shared import now, months_before
from .vault import cipher_operational_errors


class EpisodesMixin:
    def pending_episode_embeddings(self, model: str, months: int = 6,
                                   limit: int = 15) -> list[dict]:
        """Index user utterances first, then assistant responses for full recall."""
        with self.connect() as db:
            rows = db.execute('''SELECT e.* FROM conversation_episodes e
                LEFT JOIN episode_vectors v ON v.episode_id=e.id AND v.model=?
                WHERE v.episode_id IS NULL AND e.created_at>=?
                ORDER BY CASE WHEN e.role='user' THEN 0 ELSE 1 END,
                         e.created_at DESC, e.rowid DESC LIMIT ?''',
                (model, months_before(months), max(1, min(60,limit)))).fetchall()
        return [dict(row) for row in rows]

    def save_episode_vector(self, episode_id: str, model: str, values: list[float]) -> None:
        import math
        if not values or len(values)>8192 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):
            raise ValueError('Embedding inválido')
        with self.connect() as db:
            db.execute('''INSERT INTO episode_vectors(episode_id,model,vector_json,created_at)
                SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM conversation_episodes WHERE id=?)
                ON CONFLICT(episode_id,model) DO UPDATE SET
                vector_json=excluded.vector_json,created_at=excluded.created_at''',
                (episode_id,model,json.dumps(values),now(),episode_id))

    def episode_vectors_in_window(self, model: str, months: int = 6,
                                  limit: int = 10000) -> list[dict]:
        """Bounded local cosine scan; production-scale installations need ANN index."""
        with self.connect() as db:
            rows = db.execute('''SELECT e.*,v.vector_json FROM episode_vectors v
                JOIN conversation_episodes e ON e.id=v.episode_id
                WHERE v.model=? AND e.created_at>=?
                ORDER BY e.created_at DESC LIMIT ?''',
                (model,months_before(months),max(1,min(limit,10000)))).fetchall()
        return [dict(row) for row in rows]

    def has_episode_vectors(self, model: str, months: int = 6) -> bool:
        with self.connect() as db:
            return bool(db.execute("""SELECT EXISTS(
                SELECT 1 FROM episode_vectors v JOIN conversation_episodes e
                ON e.id=v.episode_id WHERE v.model=? AND e.created_at>=? LIMIT 1
            )""", (model, months_before(months))).fetchone()[0])

    def iter_episode_vectors(self, model: str, months: int = 6,
                             limit: int = 10000, batch_size: int = 128):
        """Yield only candidate id/vector pairs, preserving date and ordering."""
        limit = max(1, min(int(limit), 10000))
        batch_size = max(1, min(int(batch_size), 256))
        with self.connect() as db:
            cursor = db.execute("""SELECT e.id, v.vector_json FROM episode_vectors v
                JOIN conversation_episodes e ON e.id=v.episode_id
                WHERE v.model=? AND e.created_at>=?
                ORDER BY e.created_at DESC LIMIT ?""",
                (model, months_before(months), limit))
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    yield (row['id'], row['vector_json'])

    def episode_rows_by_ids(self, ids: list[str], months: int = 6) -> list[dict]:
        """Read only selected conversation excerpts; enforce the window again."""
        ids = list(dict.fromkeys(ids))[:50]
        if not ids:
            return []
        placeholders = ','.join('?' for _ in ids)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM conversation_episodes WHERE id IN ({placeholders}) "
                "AND created_at>=?", (*ids, months_before(months))).fetchall()
        lookup = {row['id']: dict(row) for row in rows}
        return [lookup[ident] for ident in ids if ident in lookup]

    def episode_vector_count(self, model: str, months: int = 6) -> int:
        with self.connect() as db:
            return db.execute('''SELECT count(*) FROM episode_vectors v
                JOIN conversation_episodes e ON e.id=v.episode_id
                WHERE v.model=? AND e.created_at>=?''',
                (model, months_before(months))).fetchone()[0]

    def record_exchange(self, session_id: str, user: str, assistant: str) -> list[dict]:
        """Store conversational turns atomically and independently of the UI history."""
        session_id = session_id.strip()[:64] or uuid4().hex
        if not re.fullmatch(r'[\w-]+', session_id, flags=re.UNICODE):
            session_id = uuid4().hex
        items = []
        stamp = now()
        for role, content in [('user',user), ('assistant',assistant)]:
            content = content.strip()[:3000]
            if content:
                items.append({'id':uuid4().hex[:12], 'session_id':session_id,
                              'role':role, 'content':content, 'created_at':stamp})
        with self.connect() as db:
            for entry in items:
                db.execute('INSERT INTO conversation_episodes '
                           '(id,session_id,role,content,created_at) '
                           'VALUES(:id,:session_id,:role,:content,:created_at)', entry)
        return items

    def recent_episodes(self, months: int = 6, limit: int = 30) -> list[dict]:
        cutoff = months_before(months)
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes WHERE created_at>=?
                ORDER BY created_at DESC,rowid DESC LIMIT ?''', (cutoff,max(1,min(200,limit)))).fetchall()
        return [dict(r) for r in rows]

    def episodes_months_ago(self, months: int, limit: int = 25) -> list[dict]:
        """Conversations from one specific calendar-month window (1..N ago)."""
        if months < 1:
            return []
        start, end = months_before(months), months_before(months-1)
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes
                WHERE created_at>=? AND created_at<?
                ORDER BY created_at DESC,rowid DESC LIMIT ?''',
                (start,end,max(1,min(100,limit)))).fetchall()
        return [dict(r) for r in rows]

    def search_episodes(self, query: str, months: int = 6, limit: int = 6) -> list[dict]:
        """Relevant conversations from last N calendar months; no age-based deletion."""
        words = self._terms(query)
        if not words:
            return []
        cutoff = months_before(months)
        limit = max(1,min(50,int(limit)))
        expression = ' OR '.join('"' + w.replace('"','') + '"' for w in words)
        with self.connect() as db:
            try:
                rows = db.execute('''SELECT e.*,bm25(episode_fts) AS rank FROM episode_fts
                    JOIN conversation_episodes e ON e.rowid=episode_fts.rowid
                    WHERE episode_fts MATCH ? AND e.created_at>=?
                    ORDER BY bm25(episode_fts) ASC,e.created_at DESC LIMIT ?''',
                    (expression,cutoff,limit)).fetchall()
            except cipher_operational_errors():
                parts = ['lower(content) LIKE ?'] * len(words)
                rows = db.execute('SELECT * FROM conversation_episodes WHERE created_at>=? AND ('+
                    ' OR '.join(parts)+') ORDER BY created_at DESC LIMIT ?',
                    (cutoff, *['%'+w+'%' for w in words], limit)).fetchall()
        return [dict(r) for r in rows]

    def delete_episode(self, episode_id: str) -> bool:
        with self.connect() as db:
            removed = db.execute('DELETE FROM conversation_episodes WHERE id=?',
                                 (episode_id,)).rowcount
            if removed:
                self._remove_orphan_auto_memories(db)
                from .relations import RelationMemory
                RelationMemory._clean_orphans(db)
            return bool(removed)

    def erase_episodes(self) -> int:
        """Hard-delete episodic records from active DB; backups remain unaffected."""
        with self.connect() as db:
            result = db.execute('DELETE FROM conversation_episodes')
            count = result.rowcount
            self._remove_orphan_auto_memories(db)
            from .relations import RelationMemory
            RelationMemory._clean_orphans(db)
        return count

    def episode_count(self, months: int = 6) -> int:
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM conversation_episodes WHERE created_at>=?',
                              (months_before(months),)).fetchone()[0]
