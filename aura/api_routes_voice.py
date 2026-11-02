"""Bounded local audio HTTP and continuous voice WebSocket."""
from __future__ import annotations
import asyncio
import json
import time
from fastapi import Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response
from .api_models import VoiceText
from .local_voice import VoiceInvalid, VoiceUnavailable, MAX_WAV_BYTES
from .persistent_whisper import WhisperOfflineError, MIN_PCM_BYTES, MAX_PCM_BYTES


def register_voice_routes(app, settings, local_voice, persistent_whisper):
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

