"""Bounded, in-memory voice sessions for the same-origin Expecto HTTP API.

This does not capture microphones, send text to a model, or generate audio.
Clients must explicitly connect STT -> command -> TTS adapters.
"""
from __future__ import annotations

from dataclasses import asdict
from secrets import token_urlsafe
from time import monotonic
from typing import Callable

from .voice_turns import VoiceTurns


class VoiceCapacityError(RuntimeError):
    """All voice-session slots are in use."""


class VoiceSessions:
    """Single-event-loop session store: bounded capacity and idle expiry.

    Access is deliberately synchronous and performs no awaits; request handlers
    use it on the FastAPI event loop. Do not share across worker processes.
    """

    def __init__(self, *, max_sessions: int = 8, idle_ttl: float = 600.0,
                 clock: Callable[[], float] = monotonic):
        if max_sessions < 1 or max_sessions > 128 or idle_ttl <= 0:
            raise ValueError("invalid voice session limits")
        self._max_sessions = max_sessions
        self._idle_ttl = idle_ttl
        self._clock = clock
        self._sessions: dict[str, tuple[VoiceTurns, float]] = {}

    def _prune(self) -> None:
        now = self._clock()
        for sid, (_, seen) in tuple(self._sessions.items()):
            if now - seen >= self._idle_ttl:
                del self._sessions[sid]

    def _get(self, session_id: str) -> VoiceTurns:
        self._prune()
        if session_id not in self._sessions:
            raise KeyError("voice session not found or expired")
        session, _ = self._sessions[session_id]
        self._sessions[session_id] = (session, self._clock())
        return session

    def listen(self, session_id: str | None = None) -> dict:
        self._prune()
        if session_id is None:
            if len(self._sessions) >= self._max_sessions:
                raise VoiceCapacityError("too many active voice sessions")
            session_id = token_urlsafe(24)
            while session_id in self._sessions:
                session_id = token_urlsafe(24)
            self._sessions[session_id] = (VoiceTurns(clock=self._clock), self._clock())
        session = self._get(session_id)
        return {"session_id": session_id, **asdict(session.listen())}

    def transcript(self, session_id: str, generation: int, text: str) -> dict:
        session = self._get(session_id)
        return asdict(session.transcript(text, generation=generation))

    def answer(self, session_id: str, generation: int, text: str) -> dict:
        session = self._get(session_id)
        return asdict(session.answer(generation, text))

    def finished(self, session_id: str, generation: int) -> dict:
        return asdict(self._get(session_id).finished(generation))

    def stop(self, session_id: str) -> dict:
        result = asdict(self._get(session_id).stop())
        del self._sessions[session_id]
        return result

    def status(self, session_id: str) -> dict:
        return self._get(session_id).snapshot()
