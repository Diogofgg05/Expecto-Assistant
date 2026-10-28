"""Dependency-free bounded voice turn coordinator; transports and STT/TTS are adapters."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from typing import Callable

class Phase(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

@dataclass(frozen=True)
class VoiceEvent:
    kind: str
    generation: int
    text: str = ""

class VoiceTurns:
    """Single-owner state machine. Caller serializes events on its event loop.

    Generation tokens prevent late LLM/TTS results from speaking after barge-in.
    No audio or transcripts are stored by this component.
    """
    def __init__(self, *, clock: Callable[[], float] = monotonic, max_text: int = 4000):
        if not 1 <= max_text <= 100_000:
            raise ValueError("invalid text limit")
        self.clock = clock
        self.max_text = max_text
        self.phase = Phase.IDLE
        self.generation = 0
        self.started_at = clock()

    def _move(self, phase: Phase) -> int:
        self.phase = phase
        self.started_at = self.clock()
        return self.generation

    def listen(self) -> VoiceEvent:
        self.generation += 1
        return VoiceEvent("cancel_previous", self._move(Phase.LISTENING))

    def transcript(self, text: str) -> VoiceEvent:
        if self.phase != Phase.LISTENING:
            return VoiceEvent("ignored", self.generation)
        text = text.strip()[:self.max_text]
        if not text:
            return VoiceEvent("ignored", self.generation)
        return VoiceEvent("request_llm", self._move(Phase.THINKING), text)

    def answer(self, generation: int, text: str) -> VoiceEvent:
        if generation != self.generation or self.phase != Phase.THINKING:
            return VoiceEvent("stale", self.generation)
        text = text.strip()[:self.max_text]
        if not text:
            self._move(Phase.IDLE)
            return VoiceEvent("empty", generation)
        return VoiceEvent("request_tts", self._move(Phase.SPEAKING), text)

    def finished(self, generation: int) -> VoiceEvent:
        if generation != self.generation or self.phase != Phase.SPEAKING:
            return VoiceEvent("stale", self.generation)
        self._move(Phase.IDLE)
        return VoiceEvent("idle", generation)

    def stop(self) -> VoiceEvent:
        self.generation += 1
        return VoiceEvent("cancel_previous", self._move(Phase.IDLE))

    def snapshot(self) -> dict:
        return {"phase": self.phase.value, "generation": self.generation,
                "elapsed_ms": max(0, round((self.clock() - self.started_at) * 1000))}
