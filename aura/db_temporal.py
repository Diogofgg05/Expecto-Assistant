"""TemporalMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from .db_shared import now, months_before


class TemporalMixin:
    def set_temporal_fact(self, subject: str, value: str, *,
                          source: str='explicit_user', episode_id: str | None=None,
                          quote: str='') -> dict | None:
        """Transactional current-state update preserving all earlier observations.

        valid_from records WHEN AURA LEARNED the state; not a guessed external
        event date. An auto-extracted observation requires an existing user turn.
        """
        from .temporal import canonical_subject,clean_value
        key=canonical_subject(subject) or (subject if subject in {
            'browser','sistema_operativo','distribuicao_linux','editor',
            'linguagem_programacao','modelo_ollama','modelo_ia','framework_frontend'} else None)
        cleaned=clean_value(value)
        if not key or not cleaned:
            raise ValueError('Assunto não suportado ou valor não seguro para memória temporal.')
        if source not in ('explicit_user','auto_episode'):
            raise ValueError('Origem de memória inválida.')
        if source=='auto_episode' and not episode_id:
            raise ValueError('Uma memória automática precisa de fonte.')
        with self.connect() as db:
            if source=='auto_episode':
                evidence=db.execute("SELECT content,role,created_at FROM conversation_episodes WHERE id=?",(episode_id,)).fetchone()
                if not evidence or evidence['role']!='user' or quote!=evidence['content']:
                    raise ValueError('Memória sem mensagem original verificável.')
                # Only called synchronously on newly recorded user utterances.
                # No retrospective backfill, to avoid rewriting newer states.
            current=db.execute('SELECT * FROM temporal_facts WHERE subject=? AND valid_to IS NULL',(key,)).fetchone()
            if current and current['value'].casefold()==cleaned.casefold():
                return dict(current)  # No duplicate version for repeated assertion.
            stamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
            if current:
                db.execute('UPDATE temporal_facts SET valid_to=? WHERE id=?',(stamp,current['id']))
            item=dict(id=uuid4().hex[:12],subject=key,value=cleaned,
                      valid_from=stamp,valid_to=None,recorded_at=stamp,
                      source=source,episode_id=episode_id,source_quote=quote[:3000])
            db.execute('''INSERT INTO temporal_facts(id,subject,value,valid_from,valid_to,
                recorded_at,source,episode_id,source_quote)
                VALUES (:id,:subject,:value,:valid_from,:valid_to,:recorded_at,
                        :source,:episode_id,:source_quote)''',item)
            return item

    def observe_temporal_episode(self, episode_id: str) -> dict | None:
        """Capture only declarative, first-person technical configuration updates."""
        from .temporal import extract_statement
        with self.connect() as db:
            e=db.execute('SELECT * FROM conversation_episodes WHERE id=? AND role=?',
                         (episode_id,'user')).fetchone()
        if not e:
            return None
        parsed=extract_statement(e['content'])
        if not parsed:
            return None
        return self.set_temporal_fact(parsed[0],parsed[1],source='auto_episode',
                                      episode_id=episode_id,quote=e['content'])

    def temporal_current(self, subject: str | None=None, limit: int=30) -> list[dict]:
        from .temporal import canonical_subject
        key=canonical_subject(subject) if subject else None
        if subject and key is None:
            return []
        with self.connect() as db:
            if key:
                rows=db.execute('SELECT * FROM temporal_facts WHERE subject=? AND valid_to IS NULL ORDER BY valid_from DESC LIMIT ?',
                                (key,max(1,min(limit,100)))).fetchall()
            else:
                rows=db.execute('SELECT * FROM temporal_facts WHERE valid_to IS NULL ORDER BY valid_from DESC LIMIT ?',
                                (max(1,min(limit,100)),)).fetchall()
        return [dict(x) for x in rows]

    def temporal_history(self, subject: str, months: int=6, limit: int=30) -> list[dict]:
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if key is None:
            return []
        with self.connect() as db:
            rows=db.execute('''SELECT * FROM temporal_facts
                WHERE subject=? AND (valid_from>=? OR valid_to>=? OR valid_to IS NULL)
                ORDER BY valid_from DESC LIMIT ?''',
                (key,months_before(months),months_before(months),max(1,min(limit,100)))).fetchall()
        return [dict(x) for x in rows]

    def temporal_as_of(self, subject: str, at: str) -> dict | None:
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if not key:
            return None
        try:
            point=datetime.fromisoformat(at)
            if point.tzinfo is None:
                point=point.replace(tzinfo=timezone.utc)
            at=point.astimezone(timezone.utc).isoformat(timespec='microseconds')
        except (ValueError,TypeError):
            raise ValueError('Data inválida; usa AAAA-MM-DD.')
        with self.connect() as db:
            row=db.execute('''SELECT * FROM temporal_facts WHERE subject=?
                AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)
                ORDER BY valid_from DESC LIMIT 1''',(key,at,at)).fetchone()
        return dict(row) if row else None

    def erase_temporal_subject(self, subject: str) -> int:
        """Forget every temporal version for a subject, without restoring old state."""
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if not key:
            return 0
        with self.connect() as db:
            return db.execute('DELETE FROM temporal_facts WHERE subject=?',(key,)).rowcount

    def temporal_count(self) -> int:
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM temporal_facts').fetchone()[0]

    def export_temporal_history(self) -> list[dict]:
        with self.connect() as db:
            rows=db.execute('SELECT * FROM temporal_facts ORDER BY valid_from ASC').fetchall()
        return [dict(r) for r in rows]
