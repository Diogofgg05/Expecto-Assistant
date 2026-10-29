"""Bounded circuit breaker for intermittent local Ollama transport failures.

Never retries generation, downloads models, or stores prompts.
"""
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic
from typing import Callable

@dataclass(frozen=True)
class CircuitState:
    status: str
    consecutive_failures: int
    rejected: int
    cooldown_remaining_s: float

class OllamaCircuitBreaker:
    """Event-loop-owned breaker with an exclusive half-open probe."""
    def __init__(self, *, threshold: int = 3, cooldown_s: float = 15.0,
                 clock: Callable[[], float] = monotonic):
        if not 1 <= threshold <= 20 or not 0.1 <= cooldown_s <= 3600:
            raise ValueError("invalid Ollama circuit-breaker limits")
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None
        self.probing = False
        self.rejected = 0

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if self.clock() - self.opened_at < self.cooldown_s:
            self.rejected += 1
            return False
        if self.probing:
            self.rejected += 1
            return False
        self.probing = True
        return True

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.probing = False

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()
        self.probing = False

    def release_probe(self) -> None:
        self.probing = False

    def status(self) -> CircuitState:
        if self.opened_at is None:
            stage, remaining = "closed", 0.0
        else:
            remaining = max(0.0, self.cooldown_s-(self.clock()-self.opened_at))
            stage = "open" if remaining > 0 else "half_open"
        return CircuitState(stage, self.failures, self.rejected, round(remaining,3))
