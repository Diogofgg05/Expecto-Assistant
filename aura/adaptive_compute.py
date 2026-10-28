"""Expecto 6.4: deterministic, local-first adaptive compute and admission control.

Design inspiration (not vendor code): Apple's task-specific on-device models,
AMD's resource-aware heterogeneous execution, and NVIDIA Triton's bounded
concurrency. This module does NOT implement CUDA, ROCm, NPU drivers, dynamic
batching or GPU memory measurement: Ollama owns the actual accelerator.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar


class ComputeBusyError(RuntimeError):
    """Inference queue has reached its configured limit."""


T = TypeVar("T")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_HEAVY = re.compile(
    r"\b(?:demonstra|prova|resolve|calcula|equac(?:ao|oes)|integral|derivada|"
    r"algoritmo|programa|debug|codigo|código|python|javascript|seguranca|segurança|"
    r"contradicao|contradição|analisa profundamente|investiga|arquitetura|"
    r"matriz|matrizes|álgebra|algebra|refatora|refactor|reasoning|raciocina|planeia)\b",
    re.I,
)
_FAST = re.compile(
    r"^(?:ol[áa]|bom dia|boa tarde|boa noite|obrigad[oa]|"
    r"quem [ée]s|como te chamas|diz ol[áa]|responde apenas sim ou n[aã]o)[?!. ]*$",
    re.I,
)


@dataclass(frozen=True)
class ComputePolicy:
    primary_model: str
    fast_model: str = ""
    profile: str = "balanced"  # balanced | eco | performance
    memory_budget_mb: int = 0  # 0 means unknown; never infer available VRAM
    gpu_mode: str = "auto"     # auto (Ollama chooses) | cpu (num_gpu=0)
    max_active: int = 2
    max_waiting: int = 4
    queue_timeout_s: float = 8.0

    def __post_init__(self) -> None:
        if not _MODEL.fullmatch(self.primary_model):
            raise ValueError("Invalid primary model")
        if self.fast_model and not _MODEL.fullmatch(self.fast_model):
            raise ValueError("Invalid fast model")
        if self.profile not in ("balanced", "eco", "performance"):
            raise ValueError("Invalid compute profile")
        if self.gpu_mode not in ("auto", "cpu"):
            raise ValueError("Invalid accelerator policy")
        if (self.memory_budget_mb < 0 or self.memory_budget_mb > 1_048_576 or
                not 1 <= self.max_active <= 16 or not 0 <= self.max_waiting <= 128 or
                not 0.05 <= self.queue_timeout_s <= 120):
            raise ValueError("Invalid compute limits")


@dataclass(frozen=True)
class InferencePlan:
    model: str
    tier: str
    reason: str
    options: dict
    keep_alive: str | None = None


def classify_task(question: str, *, history_len: int = 0) -> str:
    """Conservative routing hint, never an authorization or intelligence score."""
    text = question.strip()
    if history_len >= 3 or len(text) > 350 or _HEAVY.search(text):
        return "complex"
    if _FAST.fullmatch(text) and history_len == 0:
        return "quick"
    # Short single-turn statements might still need nuance. Keep primary.
    return "standard"


class AdaptiveCompute:
    """Budgeted model selection without arbitrary model names or prompt storage."""

    def __init__(self, policy: ComputePolicy):
        self.policy = policy
        self._limit = InferenceLimiter(policy.max_active, policy.max_waiting,
                                       policy.queue_timeout_s)
        self._last_tier = "none"
        self._last_reason = "not_invoked"

    @property
    def limiter(self) -> "InferenceLimiter":
        return self._limit

    def plan(self, question: str, *, history_len: int = 0,
             installed: dict[str, int | None] | None = None) -> InferencePlan:
        """Installed maps exact Ollama model IDs to on-disk size in bytes, or None.

        Fast routing requires positive evidence that a configured model is installed.
        The optional budget compares disk size * 1.3 to a user-provided budget;
        it is NOT a measurement of resident RAM or VRAM.
        """
        tier = classify_task(question, history_len=history_len)
        model = self.policy.primary_model
        reason = "primary_quality_guard"
        fast = self.policy.fast_model
        if (fast and fast != model and tier == "quick" and
                self.policy.profile != "performance"):
            if installed is None or fast not in installed:
                reason = "fast_model_not_verified"
            else:
                size = installed[fast]
                budget = self.policy.memory_budget_mb
                if budget and (size is None or size <= 0 or
                               size * 1.3 > budget * 1024 * 1024):
                    reason = "fast_model_budget_not_verified"
                else:
                    model, reason = fast, "quick_installed_fast_model"

        # Only reduce response budget for the genuine small/quick route;
        # normal reasoning retains its old output allowance.
        options: dict = {"num_predict": 450, "temperature": 0.45}
        if model == fast and model != self.policy.primary_model:
            options["num_predict"] = 160
        if self.policy.gpu_mode == "cpu":
            options["num_gpu"] = 0
        keep_alive = "0s" if self.policy.profile == "eco" else None
        self._last_tier, self._last_reason = tier, reason
        return InferencePlan(model, tier, reason, options, keep_alive)

    def status(self) -> dict:
        return {
            "version": "6.4",
            "policy": {
                "profile": self.policy.profile,
                "primary_model": self.policy.primary_model,
                "fast_model_configured": bool(self.policy.fast_model),
                "gpu_mode": self.policy.gpu_mode,
                "memory_budget_mb": self.policy.memory_budget_mb,
                "memory_budget_is_estimate": True,
                "actual_gpu_residency": "managed_by_ollama_not_measured",
                "max_active": self.policy.max_active,
                "max_waiting": self.policy.max_waiting,
            },
            "last_tier": self._last_tier,
            "last_reason": self._last_reason,
            "queue": self._limit.snapshot(),
            "privacy": "local Ollama only; no prompt content in metrics",
        }


class InferenceLimiter:
    """Bounded async queue with cancellation-safe counters and timeouts.

    Single-event-loop instance; request tasks must not share it across processes.
    """

    def __init__(self, max_active: int, max_waiting: int, queue_timeout_s: float):
        if not 1 <= max_active <= 16 or not 0 <= max_waiting <= 128 or queue_timeout_s <= 0:
            raise ValueError("Invalid limiter limits")
        self.max_active, self.max_waiting = max_active, max_waiting
        self.queue_timeout_s = queue_timeout_s
        self._semaphore = asyncio.Semaphore(max_active)
        self._lock = asyncio.Lock()
        self._active = 0
        self._waiting = 0
        self._completed = 0
        self._rejected = 0
        self._failures = 0

    def snapshot(self) -> dict:
        # Called from the owner event loop; counters hold no user content.
        return {"active": self._active, "waiting": self._waiting,
                "completed": self._completed, "rejected": self._rejected,
                "failed": self._failures}

    async def run(self, action: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            if self._active + self._waiting >= self.max_active + self.max_waiting:
                self._rejected += 1
                raise ComputeBusyError("Inference capacity reached")
            self._waiting += 1

        acquired = False
        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(),
                                       timeout=self.queue_timeout_s)
                acquired = True
                # Transfer queue->active atomically for accurate capacity checks.
                async with self._lock:
                    self._waiting -= 1
                    self._active += 1
            except BaseException:
                if not acquired:
                    async with self._lock:
                        self._waiting -= 1
                raise
            try:
                result = await action()
            except BaseException:
                async with self._lock:
                    self._failures += 1
                raise
            else:
                async with self._lock:
                    self._completed += 1
                return result
            finally:
                async with self._lock:
                    self._active -= 1
        except asyncio.TimeoutError as exc:
            async with self._lock:
                self._rejected += 1
            raise ComputeBusyError("Inference queue timed out") from exc
        finally:
            if acquired:
                self._semaphore.release()
