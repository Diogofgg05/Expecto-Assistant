"""Local system metrics, preferences and static web UI."""
from __future__ import annotations
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import ROOT


def register_system_routes(app, engine, db, settings, secure):
    @app.get('/api/resources/status')
    async def resource_status():
        """RAM and Ollama VRAM metrics are separate from personal memory status."""
        data = engine.llm.nanomemory.status()
        data['ollama'] = await engine.llm.loaded_models()
        return data

    @app.get('/api/performance/status')
    async def performance_status():
        # Only anonymous, bounded in-memory aggregates. Never expose the
        # prompt, retrieved memories, output or private context.
        return {'mode': settings.performance_mode,
                'metrics': engine.llm.metrics.summary(),
                'nanomemory': engine.llm.nanomemory.status()}

    @app.get('/api/config')
    async def config():
        return {'voice_output': settings.voice_output,
                'model': settings.ollama_model,
                'performance_mode': settings.performance_mode,
                'nanomemory': engine.llm.nanomemory.status(),
                'research_interval_hours': settings.research_interval_hours,
                'advanced_learning': db.get_option('advanced_learning_enabled','false')=='true',
                'memory_months': settings.episodic_lookback_months,
                'episodic_capture': db.capture_enabled(settings.episodic_capture),
                'private_mode': db.get_option('private_mode','false')=='true',
                'encrypted_backups_enabled':secure.enabled,
                'auto_extract':db.get_option('auto_extract_memory','true' if settings.auto_extract_memory else 'false')=='true',
                'auto_link':db.get_option('auto_link_memory','true' if settings.auto_link_memory else 'false')=='true',
                'auto_consolidate':db.get_option('auto_consolidate_memory',
                    'true' if settings.auto_consolidate_memory else 'false')=='true'}

    web_path = ROOT / 'web'
    app.mount('/static', StaticFiles(directory=web_path), name='static')

    @app.get('/')
    async def index():
        return FileResponse(web_path / 'index.html')

