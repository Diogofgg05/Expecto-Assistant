"""Single-origin HTTP API + static holographic interface. Localhost by default."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse
from ipaddress import ip_address
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import Settings, ROOT
from .api_contracts import validate_api_routes
from .database import Database
from .engine import AuraEngine
from .security import SecureBackupManager, VaultError
from .local_voice import LocalVoice, VoiceInvalid, VoiceUnavailable, MAX_WAV_BYTES
from .persistent_whisper import PersistentWhisper, WhisperOfflineError, MIN_PCM_BYTES, MAX_PCM_BYTES


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=8)
    session_id: str = Field(default="", max_length=64)


class VoiceText(BaseModel):
    text: str = Field(min_length=1, max_length=240)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir / 'aura.sqlite3', passphrase=settings.database_passphrase,
                  require_encryption=settings.database_encryption_required)
    engine = AuraEngine(settings, db)
    # Lazily instantiate optional speech services. Text-only startup avoids
    # importing CTranslate2/Piper when a user never enables voice.
    @lru_cache(maxsize=1)
    def local_voice():
        return LocalVoice(settings)

    @lru_cache(maxsize=1)
    def persistent_whisper():
        return PersistentWhisper(settings)
    secure = SecureBackupManager(db, settings.data_dir / 'secure_backups', settings.backup_passphrase)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        worker = asyncio.create_task(engine.research_daemon(stop))
        memory_worker = asyncio.create_task(engine.memory_daemon(stop))
        async def backup_loop():
            while not stop.is_set():
                try:
                    if secure.enabled:
                        await asyncio.to_thread(secure.backup_if_due, settings.memory_backup_days)
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
        await engine.llm.aclose()
        await engine.memory.aclose()

    app = FastAPI(title='Expecto Ultimate API', version='7.0.5', lifespan=lifespan)
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
    app.state.db = db
    app.state.settings = settings

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'version': '7.0.5',
                'ollama': await engine.llm.health(), 'research_jobs': len(db.jobs(True))}

    def finalize_command(payload: Message, result: dict) -> dict:
        """Capture once, only after a complete response (never partial tokens)."""
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
        result.pop('capture', None)
        return result

    @app.post('/api/command')
    async def command(payload: Message):
        return finalize_command(payload, await engine.command(payload.message, payload.history))

    @app.post('/api/command/stream')
    async def command_stream(payload: Message):
        """Backpressure-aware NDJSON. The usual intent router remains authoritative.

        Events: token{text}, final{payload}, error{message}. Disconnecting
        cancels in-flight model generation; incomplete exchanges are not saved.
        """
        async def generate():
            queue = asyncio.Queue(maxsize=128)
            began = time.perf_counter()
            first_token = None

            async def on_token(piece: str):
                nonlocal first_token
                if first_token is None:
                    first_token = time.perf_counter()
                await queue.put({'type': 'token', 'text': piece})

            async def work():
                try:
                    result = await engine.command(payload.message, payload.history, on_token=on_token)
                    result = finalize_command(payload, result)
                    await queue.put({'type': 'final', 'payload': result,
                                     'metrics': {
                                         'ttft_ms': round((first_token - began) * 1000, 1)
                                                    if first_token is not None else None,
                                         'total_ms': round((time.perf_counter() - began) * 1000, 1)
                                     }})
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logging.getLogger('aura').exception('Streaming command failed')
                    await queue.put({'type': 'error',
                                     'message': 'Não foi possível concluir a resposta.'})
                finally:
                    # Under normal completion flush every token, including a full queue.
                    # If the HTTP reader disconnects, the producer is cancelled;
                    # do not wait for an abandoned queue.
                    if not asyncio.current_task().cancelling():
                        await queue.put(None)

            task = asyncio.create_task(work())
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n'
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(generate(), media_type='application/x-ndjson',
                                 headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store'})

    @app.get('/api/voice/capabilities')
    async def voice_capabilities():
        """Feature detection without exposing private machine paths."""
        return {**local_voice().capabilities(), **persistent_whisper().capabilities()}

    @app.websocket('/api/voice/continuous')
    async def continuous_voice(websocket: WebSocket):
        """One explicit local connection; PCM blocks, bounded partial updates.

        Client sends little-endian PCM16 byte frames, and JSON {"type":"flush"}
        to finalize a turn. A partial is returned at most once per 2 seconds
        after enough audio, without reloading the model.
        """
        from ipaddress import ip_address
        peer = websocket.client.host if websocket.client else ''
        try:
            local_peer = ip_address(peer).is_loopback
        except ValueError:
            local_peer = peer == 'testclient'
        origin = websocket.headers.get('origin')
        if (not local_peer or (origin and origin not in (
                'http://127.0.3.1:8000', 'http://localhost:8000',
                f'http://{settings.host}:{settings.port}'))):
            await websocket.close(code=1008)
            return
        if not persistent_whisper().available:
            await websocket.close(code=1013)
            return
        await websocket.accept()
        pcm = bytearray()
        last_partial_at = time.monotonic()
        partial_task = None
        generation = 0
        async def partial_result(audio: bytes, sequence: int):
            try:
                result = await persistent_whisper().transcribe_pcm(audio, partial=True)
                if sequence == generation:
                    await websocket.send_json({'type': 'partial', **result})
            except (WhisperOfflineError, WebSocketDisconnect, RuntimeError):
                pass
        try:
            while True:
                message = await websocket.receive()
                if message['type'] == 'websocket.disconnect':
                    break
                raw = message.get('bytes')
                if raw is not None:
                    if len(raw) % 2 or len(pcm) + len(raw) > MAX_PCM_BYTES:
                        await websocket.send_json({'type':'error','reason':'audio_limit'})
                        await websocket.close(code=1009)
                        return
                    pcm.extend(raw)
                    # At most one partial per ~2 s to protect old CPUs.
                    if len(pcm) >= 2 * 16000 * 2 and time.monotonic() - last_partial_at >= 2:
                        last_partial_at = time.monotonic()
                        sample = bytes(pcm[-min(len(pcm), 5 * 16000 * 2):])
                        if partial_task is None or partial_task.done():
                            partial_task = asyncio.create_task(partial_result(sample, generation))
                elif message.get('text'):
                    try:
                        command = json.loads(message['text'])
                    except (ValueError, TypeError):
                        await websocket.close(code=1003)
                        return
                    if command.get('type') == 'flush':
                        generation += 1  # Prevent stale provisional text after final result.
                        if partial_task is not None:
                            partial_task.cancel()
                        if len(pcm) >= MIN_PCM_BYTES:
                            try:
                                result = await persistent_whisper().transcribe_pcm(bytes(pcm))
                                await websocket.send_json({'type':'final', **result})
                            except WhisperOfflineError:
                                await websocket.send_json({'type':'error','reason':'transcription_failed'})
                        else:
                            await websocket.send_json({'type':'final','text':'','partial':False})
                        pcm.clear()
                    elif command.get('type') == 'cancel':
                        generation += 1
                        if partial_task is not None: partial_task.cancel()
                        pcm.clear()
                    else:
                        await websocket.close(code=1003)
                        return
        except WebSocketDisconnect:
            pass
        finally:
            if partial_task is not None:
                partial_task.cancel()

    @app.post('/api/voice/transcribe')
    async def voice_transcribe(request: Request):
        """Accept only bounded WAV PCM input. Never upload to a third party."""
        if not local_voice().stt_available:
            raise HTTPException(503, 'Whisper local não está configurado.')
        if request.headers.get('content-type', '').split(';', 1)[0].lower() != 'audio/wav':
            raise HTTPException(415, 'Envia áudio WAV PCM16 mono 16 kHz.')
        size = 0
        pieces = []
        async for piece in request.stream():
            size += len(piece)
            if size > MAX_WAV_BYTES:
                raise HTTPException(413, 'Gravação demasiado grande.')
            pieces.append(piece)
        try:
            return await local_voice().transcribe(b''.join(pieces))
        except VoiceInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except VoiceUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post('/api/voice/synthesize')
    async def voice_synthesize(payload: VoiceText):
        """Optional local PCM voice output for short text segments."""
        if not local_voice().tts_available:
            raise HTTPException(503, 'Piper local não está configurado.')
        try:
            wav = await local_voice().synthesize(payload.text)
        except VoiceInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except VoiceUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(wav, media_type='audio/wav',
                        headers={'Cache-Control': 'no-store'})

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

    validate_api_routes(app)
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
