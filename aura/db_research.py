"""ResearchMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from .db_shared import now, months_before


class ResearchMixin:
    def remember_document(self, topic: str, title: str, content: str, url: str,
                          source_type: str, evidence_level: str) -> dict:
        item = {
            'id': uuid4().hex[:12], 'topic': topic[:160], 'title': title[:240],
            'content': content[:8000], 'url': url[:1500],
            'source_type': source_type, 'evidence_level': evidence_level,
            'learned_at': now(),
        }
        with self.connect() as db:
            db.execute('''INSERT INTO knowledge(id, topic, title, content, url, source_type,
                evidence_level, learned_at) VALUES (:id, :topic, :title, :content, :url,
                :source_type, :evidence_level, :learned_at)
                ON CONFLICT(topic, url) DO UPDATE SET
                title=excluded.title, content=excluded.content,
                evidence_level=excluded.evidence_level, learned_at=excluded.learned_at''', item)
        return item

    def documents(self, query: str = '', limit: int = 30) -> list[dict]:
        with self.connect() as db:
            if query.strip():
                pattern = '%' + query.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
                rows = db.execute('''SELECT * FROM knowledge
                    WHERE topic LIKE ? ESCAPE '!' OR title LIKE ? ESCAPE '!' OR content LIKE ? ESCAPE '!'
                    ORDER BY learned_at DESC LIMIT ?''', (pattern, pattern, pattern, limit)).fetchall()
            else:
                rows = db.execute('SELECT * FROM knowledge ORDER BY learned_at DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create_job(self, topic: str, interval_hours: int = 24) -> dict:
        item = {'id': uuid4().hex[:12], 'topic': topic[:160],
                'interval_hours': max(6, min(interval_hours, 168)), 'created_at': now()}
        with self.connect() as db:
            db.execute('''INSERT INTO research_jobs(id, topic, enabled, interval_hours, created_at)
                VALUES (:id, :topic, 1, :interval_hours, :created_at)
                ON CONFLICT(topic) DO UPDATE SET enabled=1, interval_hours=excluded.interval_hours''', item)
        return item

    def jobs(self, enabled_only: bool = False) -> list[dict]:
        with self.connect() as db:
            if enabled_only:
                rows = db.execute('SELECT * FROM research_jobs WHERE enabled=1 ORDER BY created_at').fetchall()
            else:
                rows = db.execute('SELECT * FROM research_jobs ORDER BY created_at').fetchall()
        return [dict(r) for r in rows]

    def disable_job(self, topic: str) -> bool:
        with self.connect() as db:
            n = db.execute('UPDATE research_jobs SET enabled=0 WHERE lower(topic)=lower(?) AND enabled=1', (topic,)).rowcount
        return bool(n)

    def job_result(self, topic: str, error: str = '') -> None:
        with self.connect() as db:
            db.execute('UPDATE research_jobs SET last_run_at=?, last_error=? WHERE topic=?', (now(), error[:400], topic))

    def due_jobs(self) -> list[dict]:
        current = datetime.now(timezone.utc)
        due = []
        for job in self.jobs(True):
            try:
                prior = datetime.fromisoformat(job['last_run_at']) if job['last_run_at'] else None
            except ValueError:
                prior = None
            if prior is None or current - prior >= timedelta(hours=job['interval_hours']):
                due.append(job)
        return due[:3]  # Resource bound per scheduled cycle.
