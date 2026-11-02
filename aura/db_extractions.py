"""ExtractionsMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
from uuid import uuid4
from .db_shared import now, months_before


class ExtractionsMixin:
    def unprocessed_user_episodes(self, months: int = 6, limit: int = 3) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT e.* FROM conversation_episodes e
                LEFT JOIN extraction_processed p ON p.episode_id=e.id
                WHERE p.episode_id IS NULL AND e.role='user' AND e.created_at>=?
                ORDER BY e.created_at ASC,e.rowid ASC LIMIT ?''',
                (months_before(months),max(1,min(limit,30)))).fetchall()
        return [dict(row) for row in rows]

    def extracted_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM memories WHERE source='auto_episode' AND status='active'").fetchone()[0]

    def save_extractions(self, episode_id: str, candidates: list[dict]) -> int:
        """Store only exact quotes from a user episode; keep evidence links.

        Distinct from explicit notes. Removing the source episode purges any auto
        memory that has no other supporting episode.
        """
        from .privacy import safe_to_extract
        count=0
        with self.connect() as db:
            ep = db.execute("SELECT content,role FROM conversation_episodes WHERE id=?",(episode_id,)).fetchone()
            if ep is None or ep['role']!='user':
                return 0
            source_text=ep['content']
            for entry in candidates[:4]:
                if not isinstance(entry,dict):
                    continue
                quote=entry.get('quote','')
                category=entry.get('category','')
                if (not isinstance(quote,str) or not isinstance(category,str)
                    or category not in ('preference','project','experience')):
                    continue
                quote=quote.strip()
                if (len(quote)<15 or len(quote)>320 or quote.casefold() not in source_text.casefold()
                    or not safe_to_extract(quote)):
                    continue
                existing=db.execute("SELECT id,source FROM memories WHERE status='active' AND lower(content)=lower(?) LIMIT 1",(quote,)).fetchone()
                if existing and existing['source']!='auto_episode':
                    continue  # Never co-opt an explicit user-authored memory.
                memory_id = existing['id'] if existing else uuid4().hex[:12]
                if not existing:
                    db.execute('''INSERT INTO memories(id,content,created_at,updated_at,
                        category,topic,source,status,importance)
                        VALUES(?,?,?,?,?,?,?,?,?)''',
                        (memory_id,quote,now(),now(),category,'','auto_episode','active',3))
                    count+=1
                db.execute('''INSERT OR IGNORE INTO automatic_evidence
                    (memory_id,episode_id,quote,extracted_at) VALUES(?,?,?,?)''',
                    (memory_id,episode_id,quote,now()))
            db.execute('''INSERT INTO extraction_processed(episode_id,completed_at,outcome)
                VALUES(?,?,?) ON CONFLICT(episode_id) DO UPDATE SET
                completed_at=excluded.completed_at,outcome=excluded.outcome''',
                (episode_id,now(),'checked'))
        return count

    def _remove_orphan_auto_memories(self, db):
        db.execute('''DELETE FROM memories WHERE source='auto_episode'
            AND id NOT IN (SELECT memory_id FROM automatic_evidence)''')
