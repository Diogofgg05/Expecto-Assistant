"""Command HTTP/NDJSON routes, preserving the intent boundary."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from contextlib import suppress
from fastapi.responses import StreamingResponse
from .api_models import Message


def register_command_routes(app, engine, db, settings):
    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'version': '7.0.6',
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

