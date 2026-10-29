"""Single-origin HTTP API + static holographic interface. Localhost by default."""
from __future__ import annotations
import asyncio
import logging
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse
from ipaddress import ip_address
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import Settings, ROOT
from .database import Database
from .engine import AuraEngine
from .security import VaultError
from .voice_sessions import VoiceSessions, VoiceCapacityError
from .local_stt import LocalSpeech, STTUnavailable, STTInvalidAudio


class VoiceListen(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)


class VoicePayload(BaseModel):
    session_id: str = Field(min_length=10, max_length=128)
    generation: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)


class VoiceGeneration(BaseModel):
    session_id: str = Field(min_length=10, max_length=128)
    generation: int = Field(ge=1)


class VoiceStop(BaseModel):
    session_id: str = Field(min_length=10, max_length=128)


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=8)
    session_id: str = Field(default="", max_length=64)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir / 'aura.sqlite3', passphrase=settings.database_passphrase,
                  require_encryption=settings.database_encryption_required)
    engine = AuraEngine(settings, db)
    voice_sessions = VoiceSessions()
    local_speech = LocalSpeech(settings.local_stt_model_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        worker = asyncio.create_task(engine.research_daemon(stop))
        memory_worker = asyncio.create_task(engine.memory_daemon(stop))
        async def backup_loop():
            while not stop.is_set():
                try:
                    if len(settings.backup_passphrase) >= 12:
                        await asyncio.to_thread(engine.secure_backups.backup_if_due,
                                                settings.memory_backup_days)
                except (OSError, ValueError):
                    logging.getLogger('aura').exception('Não foi possível criar backup automático')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=3600)
                except asyncio.TimeoutError:
                    pass
        backups = asyncio.create_task(backup_loop())
        yield
        stop.set()
        worker.cancel()
        memory_worker.cancel()
        backups.cancel()
        for task in (worker, memory_worker, backups):
            with suppress(asyncio.CancelledError):
                await task
        # Never instantiate the Ollama chiplet merely to close its sockets.
        llm = engine.__dict__.get('llm')
        if llm is not None:
            await llm.close()
        # Both inference and embedding transports are lazy: shut down only
        # the instances that were actually activated during this lifespan.
        memory = engine.__dict__.get('memory')
        if memory is not None:
            await memory.close()

    app = FastAPI(title='Expecto Ultimate API', version='3.3.0-fact-verification', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def protect_local_origin(request: Request, call_next):
        # The API contains private data; never serve external client IPs, even
        # if someone overrides the Host header to bypass host allowlisting.
        remote = request.client.host if request.client else ''
        try:
            local_peer = ip_address(remote).is_loopback
        except ValueError:
            local_peer = remote == 'testclient'  # Starlette's in-process TestClient
        if not local_peer:
            return JSONResponse({'detail':'AURA disponível apenas localmente.'}, status_code=403)
        # Prevent browser cross-site POSTs and DNS rebinding to local API.
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin')
            if origin:
                o = urlparse(origin)
                host = request.url.hostname
                port = request.url.port or 80
                origin_port = o.port or (443 if o.scheme == 'https' else 80)
                if (o.scheme not in {'http', 'https'} or o.hostname != host or
                        origin_port != port):
                    return JSONResponse({'detail':'Pedido de outra origem recusado.'}, status_code=403)
            fetch_site = request.headers.get('sec-fetch-site', '')
            if fetch_site in {'cross-site', 'same-site'} and not origin:
                return JSONResponse({'detail':'Pedido entre origens recusado.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; media-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        return response
    app.state.engine = engine
    app.state.voice_sessions = voice_sessions
    app.state.local_speech = local_speech
    app.state.db = db
    app.state.settings = settings

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'version': '3.3.0-fact-verification',
                'ollama': await engine.llm.health(), 'research_jobs': len(db.jobs(True))}

    # Local session control only. No microphone, transcription or TTS backend is
    # started by these routes. No text or audio is persisted by VoiceSessions.
    @app.get('/api/voice/diagnostics')
    async def voice_diagnostics():
        return local_speech.status()

    @app.post('/api/voice/transcribe')
    async def voice_transcribe(request: Request):
        # No multipart dependency or persistent files. Hard cap before reading.
        if not local_speech.configured:
            raise HTTPException(503, 'Reconhecimento local não configurado')
        length = request.headers.get('content-length')
        if length:
            try:
                if int(length) > LocalSpeech.MAX_AUDIO_BYTES:
                    raise HTTPException(413, 'Áudio demasiado grande')
            except ValueError:
                raise HTTPException(400, 'Content-Length inválido')
        mime = request.headers.get('content-type', '').split(';', 1)[0].lower().strip()
        if mime not in LocalSpeech.ALLOWED_TYPES:
            raise HTTPException(415, 'Formato de áudio não suportado')
        audio = bytearray()
        async for chunk in request.stream():
            audio.extend(chunk)
            if len(audio) > LocalSpeech.MAX_AUDIO_BYTES:
                raise HTTPException(413, 'Áudio demasiado grande')
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(local_speech.transcribe, bytes(audio), mime), timeout=75)
            return {'text': text, 'language': 'pt', 'source': 'local_offline'}
        except STTUnavailable as exc:
            raise HTTPException(503, str(exc))
        except STTInvalidAudio as exc:
            raise HTTPException(422, str(exc))
        except asyncio.TimeoutError:
            raise HTTPException(504, 'Tempo limite da transcrição excedido')

    @app.post('/api/voice/listen')
    async def voice_listen(payload: VoiceListen):
        try:
            return voice_sessions.listen(payload.session_id)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')
        except VoiceCapacityError:
            raise HTTPException(429, 'Too many active voice sessions')

    @app.post('/api/voice/transcript')
    async def voice_transcript(payload: VoicePayload):
        try:
            return voice_sessions.transcript(payload.session_id, payload.generation, payload.text)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')

    @app.post('/api/voice/answer')
    async def voice_answer(payload: VoicePayload):
        try:
            return voice_sessions.answer(payload.session_id, payload.generation, payload.text)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')

    @app.post('/api/voice/finished')
    async def voice_finished(payload: VoiceGeneration):
        try:
            return voice_sessions.finished(payload.session_id, payload.generation)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')

    @app.post('/api/voice/stop')
    async def voice_stop(payload: VoiceStop):
        try:
            return voice_sessions.stop(payload.session_id)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')

    @app.get('/api/voice/status/{session_id}')
    async def voice_status(session_id: str):
        try:
            return voice_sessions.status(session_id)
        except KeyError:
            raise HTTPException(404, 'Voice session not found')

    @app.get('/api/reasoning/status')
    async def reasoning_status():
        # Read-only. Never loads a model, reads a conversation or starts research.
        return {"version": "6.5", **engine.reasoning_runtime.status(),
                "exact_algebra": "bounded rational solver, no LLM",
                "quality_goal": "16/20 is not certified without held-out real-model evaluations"}

    @app.get('/api/compute/status')
    async def compute_status():
        # Constructing the LLM chiplet is local-only and does not load Ollama weights.
        return engine.llm.compute_status()

    @app.get('/api/performance/status')
    async def performance_status():
        """Read-only, aggregate-only. Never requests Ollama or stores prompts."""
        return {
            **engine.llm.performance.status(),
            'resource_guard': engine.llm.resource_guard.status(),
        }

    @app.get('/api/chiplets')
    async def chiplet_metrics():
        """Read-only service-status snapshot; never activates standby modules."""
        return engine.chiplet_status()

    def persist_command(payload: Message, result: dict) -> None:
        # Preserve the existing privacy and retention rules for both transports.
        if (result.get('capture') and db.capture_enabled(settings.episodic_capture) and
            db.get_option('private_mode','false') != 'true'):
            from .privacy import safe_to_capture
            if safe_to_capture(payload.message):
                episodes = db.record_exchange(payload.session_id, payload.message, result.get('text',''))
                if (episodes and episodes[0]['role']=='user' and
                    db.get_option('auto_extract_memory','true' if settings.auto_extract_memory else 'false')=='true'):
                    db.observe_temporal_episode(episodes[0]['id'])
                    if db.get_option('auto_link_memory','true' if settings.auto_link_memory else 'false')=='true':
                        engine.relations.observe_episode(episodes[0]['id'])

    @app.post('/api/command')
    async def command(payload: Message):
        result = await engine.command(payload.message, payload.history)
        persist_command(payload, result)
        result.pop('capture', None)
        return result

    @app.post('/api/command/stream')
    async def command_stream(payload: Message):
        """Same trusted command router as /api/command; provisional LLM tokens
        are followed by one final verified response. No token is a tool command.
        """
        async def iterator():
            queue = asyncio.Queue(maxsize=32)

            async def token_sink(token: str):
                await queue.put({'type':'token', 'text':token})

            async def producer():
                try:
                    result = await engine.command(payload.message, payload.history,
                                                  on_token=token_sink)
                    persist_command(payload, result)
                    result.pop('capture', None)
                    await queue.put({'type':'final','payload':result})
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logging.getLogger('aura').exception('Streaming command failed')
                    await queue.put({'type':'error', 'message':
                                     'O processamento falhou. Tenta novamente.'})
                finally:
                    await queue.put({'type':'end'})

            task = asyncio.create_task(producer())
            try:
                while True:
                    item = await queue.get()
                    if item['type']=='end':
                        break
                    yield 'data: ' + json.dumps(item,ensure_ascii=False) + '\n\n'
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

        return StreamingResponse(iterator(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-store', 'X-Accel-Buffering':'no'})

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
                'encrypted_backups_enabled':len(settings.backup_passphrase) >= 12,
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

    @app.get('/api/optimizer/status')
    async def optimizer_status():
        # Read-only summary, no training from HTTP requests.
        return engine.optimizer.status()

    @app.get('/api/learning/status')
    async def learning_status():
        return {'enabled':db.get_option('advanced_learning_enabled','false')=='true',
                **engine.learning.stats()}

    @app.get('/api/learning/claims')
    async def learning_claims(topic: str = '', limit: int = 25):
        return {'items':engine.learning.claims(topic[:160],min(max(limit,1),50))}

    @app.get('/api/epistemics/claims/{claim_id}')
    async def epistemic_claim(claim_id: str):
        try: result=engine.epistemics.assess(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/epistemics/audits')
    async def epistemic_audits(limit: int = 20):
        return {'items':engine.epistemics.latest(min(100,max(1,limit)))}

    @app.get('/api/quality/claims/{claim_id}')
    async def quality_claim(claim_id: str):
        try: result=engine.quality.inspect(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/factcheck/history')
    async def factual_history(limit: int = 20):
        return {'items':engine.factcheck.latest(limit)}

    @app.get('/api/factcheck/claims/{claim_id}')
    async def factual_claim(claim_id: str):
        try: result=engine.factcheck.offline(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/quality/summary')
    async def quality_summary(limit: int = 25):
        return engine.quality.overview(limit)

    @app.get('/api/config')
    async def config():
        return {'voice_output': settings.voice_output,
                'model': settings.ollama_model,
                'research_interval_hours': settings.research_interval_hours,
                'advanced_learning': db.get_option('advanced_learning_enabled','false')=='true',
                'memory_months': settings.episodic_lookback_months,
                'episodic_capture': db.capture_enabled(settings.episodic_capture),
                'private_mode': db.get_option('private_mode','false')=='true',
                'encrypted_backups_enabled':len(settings.backup_passphrase) >= 12,
                'auto_extract':db.get_option('auto_extract_memory','true' if settings.auto_extract_memory else 'false')=='true',
                'auto_link':db.get_option('auto_link_memory','true' if settings.auto_link_memory else 'false')=='true',
                'auto_consolidate':db.get_option('auto_consolidate_memory',
                    'true' if settings.auto_consolidate_memory else 'false')=='true'}

    web_path = ROOT / 'web'
    app.mount('/static', StaticFiles(directory=web_path), name='static')

    @app.get('/')
    async def index():
        return FileResponse(web_path / 'index.html')

    return app


class DeferredASGI:
    """Do not read or create private memory during Python import."""
    def __init__(self):
        self._app = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = DeferredASGI()
