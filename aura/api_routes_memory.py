"""Memory, timeline, relations and consolidation HTTP routes."""
from __future__ import annotations
import asyncio
from fastapi import HTTPException


def register_memory_routes(app, engine, db, settings, secure):
    @app.get('/api/panel/{name}')
    async def panel(name: str):
        if name not in {'memory', 'research', 'jobs', 'diagnostics', 'projects', 'browser'}:
            raise HTTPException(404, 'Unknown panel')
        return {'panel': name, 'data': await engine.panel_data(name)}

    @app.get('/api/memory/search')
    async def memory_search(q: str = '', limit: int = 10):
        if not q.strip():
            return {'items': []}
        return {'items': await engine.memory.recall(q[:250], max(1, min(limit, 20)))}

    @app.get('/api/memory/conversations/search')
    async def episode_search(q: str = '', limit: int = 10):
        if not q.strip():
            return {'items':[]}
        return {'items':await engine.memory.recall_episodes(q[:250],settings.episodic_lookback_months,max(1,min(limit,20)))}

    @app.post('/api/memory/index-conversations')
    async def index_conversations():
        return await engine.memory.index_episode_pending(settings.episodic_lookback_months,20)

    @app.post('/api/memory/extract-knowledge')
    async def extract_knowledge():
        return await engine.extractor.extract_one()

    @app.get('/api/memory/status')
    async def memory_status():
        return {'lookback_months':settings.episodic_lookback_months,
                'recording':db.capture_enabled(settings.episodic_capture),
                'episodes_in_window':db.episode_count(settings.episodic_lookback_months),
                'embedding_model':settings.embedding_model,
                'episodes_indexed':db.episode_vector_count(settings.embedding_model,settings.episodic_lookback_months) if settings.embedding_model else 0,
                'auto_extract':db.get_option('auto_extract_memory','true' if settings.auto_extract_memory else 'false')=='true',
                'auto_memories':db.extracted_count(),
                'temporal_facts':db.temporal_count(),
                'temporal_current':len(db.temporal_current()),
                'relational_graph':engine.relations.stats(),
                'auto_link_memory':db.get_option('auto_link_memory','true' if settings.auto_link_memory else 'false')=='true',
                'auto_consolidate_memory':db.get_option('auto_consolidate_memory',
                    'true' if settings.auto_consolidate_memory else 'false')=='true',
                'consolidation':engine.consolidation.stats(),
                'no_automatic_deletion':True,
                'private_mode': db.get_option('private_mode','false')=='true',
                'encrypted_backups_enabled':secure.enabled,
                'active_database_encrypted':db.encrypted,
                'database_path':str(db.path)}

    @app.get('/api/memory/temporal/current')
    async def temporal_current(subject: str = ''):
        return {'items':db.temporal_current(subject or None)}

    @app.get('/api/memory/temporal/history')
    async def temporal_history(subject: str = ''):
        return {'items':db.temporal_history(subject,settings.episodic_lookback_months)}

    @app.get('/api/memory/temporal/as-of')
    async def temporal_as_of(subject: str, date: str):
        try:
            return {'item':db.temporal_as_of(subject,date)}
        except ValueError as exc:
            raise HTTPException(status_code=400,detail=str(exc))

    @app.get('/api/memory/relations')
    async def memory_relations(name: str = '', kind: str = '', limit: int = 30):
        return {'items':engine.relations.list_links(
            name=name or None,kind=kind or None,
            months=settings.episodic_lookback_months,limit=limit)}

    @app.get('/api/memory/relations/search')
    async def search_relations(q: str = ''):
        return {'items':engine.relations.search_related(q[:250],months=settings.episodic_lookback_months)}

    @app.get('/api/memory/consolidation/status')
    async def consolidation_status():
        return engine.consolidation.stats()

    @app.get('/api/memory/consolidation/summaries')
    async def consolidation_summaries(topic: str = '', limit: int = 15):
        return {'items':engine.consolidation.summaries(topic[:120],limit)}

    @app.get('/api/memory/consolidation/review')
    async def consolidation_review():
        return {'duplicates':engine.consolidation.duplicate_candidates(),
                'possible_conflicts_and_changes':engine.consolidation.review_candidates()}

    @app.post('/api/memory/consolidation/run')
    async def consolidation_run():
        return await asyncio.to_thread(engine.consolidation.consolidate,
                                       settings.episodic_lookback_months)

