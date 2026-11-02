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
from .api_routes_commands import register_command_routes
from .api_routes_voice import register_voice_routes
from .api_routes_memory import register_memory_routes
from .api_routes_knowledge import register_knowledge_routes
from .api_routes_system import register_system_routes
from .database import Database
from .engine import AuraEngine
from .security import SecureBackupManager, VaultError
from .local_voice import LocalVoice, VoiceInvalid, VoiceUnavailable, MAX_WAV_BYTES
from .persistent_whisper import PersistentWhisper, WhisperOfflineError, MIN_PCM_BYTES, MAX_PCM_BYTES


from .api_models import Message, VoiceText


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

    app = FastAPI(title='Expecto Ultimate API', version='7.0.6', lifespan=lifespan)
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

    # Preserve route registration order after modular extraction.
    register_command_routes(app, engine, db, settings)
    register_voice_routes(app, settings, local_voice, persistent_whisper)
    register_memory_routes(app, engine, db, settings, secure)
    register_knowledge_routes(app, engine, db)
    register_system_routes(app, engine, db, settings, secure)

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
