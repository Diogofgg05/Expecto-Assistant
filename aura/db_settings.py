"""SettingsMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from .db_shared import now, months_before


class SettingsMixin:
    def get_option(self, key: str, default: str = '') -> str:
        with self.connect() as db:
            row = db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_option(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO app_settings(key,value) VALUES(?,?) '
                       'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,value))

    def capture_enabled(self, default: bool = True) -> bool:
        return self.get_option('episodic_capture', 'true' if default else 'false') == 'true'

    def export_full_memory(self, months: int = 6) -> dict:
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes WHERE created_at>=?
                ORDER BY created_at ASC,rowid ASC''', (months_before(months),)).fetchall()
            links = db.execute('''SELECT a.memory_id,a.episode_id,a.quote,a.extracted_at
                FROM automatic_evidence a JOIN conversation_episodes e ON e.id=a.episode_id
                WHERE e.created_at>=?''', (months_before(months),)).fetchall()
        from .relations import RelationMemory
        from .consolidation import ConsolidationEngine
        return {'version': '2.6', 'exported_at': now(), 'lookback_months': months,
                'notes': self.export_memories(), 'conversations': [dict(x) for x in rows],
                'automatic_evidence': [dict(x) for x in links],
                'temporal_history': self.export_temporal_history(),
                'relational_graph': RelationMemory(self).export_graph(),
                'consolidation_summaries': ConsolidationEngine(self).summaries()}

    def backup_if_due(self, folder: Path, days: int = 7) -> Path | None:
        """Make consistent backups weekly, without auto-deleting old ones."""
        last = self.get_option('last_backup_at', '')
        try:
            prior = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - prior < timedelta(days=days):
                return None
        except (ValueError, TypeError):
            pass
        dest = self.backup(folder)
        self.set_option('last_backup_at', now())
        return dest

    def combined_memory_panel(self, months: int = 6) -> list[dict]:
        """One existing holographic memory panel; no new pages or navigation."""
        notes = self.memories(30)
        with self.connect() as conn:
            sources = conn.execute('SELECT memory_id,group_concat(episode_id) AS episode_ids FROM automatic_evidence GROUP BY memory_id').fetchall()
        evidence = {r['memory_id']:r['episode_ids'] for r in sources}
        for note in notes:
            if note.get('source')=='auto_episode':
                note['evidence_episode_ids'] = evidence.get(note['id'],'')
        conversations = self.recent_episodes(months, 25)
        from .temporal import DISPLAY
        temporal = [{**t, 'category':'temporal', 'content':(
            DISPLAY.get(t['subject'],t['subject']) + ': ' + t['value']),
            'created_at':t['valid_from'], 'updated_at':t['valid_from'],
            'temporal_state':'current'} for t in self.temporal_current(limit=15)]
        from .relations import RelationMemory, DISPLAY as GRAPH_DISPLAY
        graph = [{**edge, 'category':'relation',
            'content': (GRAPH_DISPLAY.get(edge['source_kind'],edge['source_kind'])+' '+edge['source_name']+' '+
                        GRAPH_DISPLAY.get(edge['relation_type'],edge['relation_type'])+' '+
                        GRAPH_DISPLAY.get(edge['target_kind'],edge['target_kind'])+' '+edge['target_name']),
            'created_at':edge['created_at'], 'updated_at':edge['created_at']}
            for edge in RelationMemory(self).list_links(limit=25,months=months)]
        from .consolidation import ConsolidationEngine
        summaries = [{**item, 'category':'summary',
            'content':item['content'], 'updated_at':item['created_at']}
            for item in ConsolidationEngine(self).summaries(limit=8)]
        result = summaries + graph + temporal + notes + [{**e, 'category':'conversation',
                            'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']}
                           for e in conversations]
        return sorted(result, key=lambda e:e['created_at'], reverse=True)
