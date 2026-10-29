"""Expecto Performance Engine 4.0: conservative routing and bounded private metrics.

No extra process, network probe, prompt logging, or hardware claims.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median
from time import perf_counter
import math
import re
import unicodedata


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


# Only standalone, definitional questions take the context-free route.
# Everything ambiguous, personal, time-dependent or conversational stays full.
_GENERAL = re.compile(
    r"^(?:o que (?:e|sao)|define|explica (?:o que e|o conceito de)|"
    r"qual (?:e )?(?:a )?(?:definicao|significado) de)\s+"
    r"(?:um |uma |o |a |os |as )?"
    r"[\w\s-]{3,100}[?.!]*$", re.I,
)
_CONTEXT = re.compile(
    r"\b(?:eu|meu|minha|meus|minhas|nosso|nossa|tu|teu|tua|"
    r"ontem|hoje|amanha|agora|atual|202[0-9]|lembras|recordas|"
    r"expecto|aura|projeto|ficheiro|arquivo|conversa|"
    r"anterior|ultimo|ultima|disseste|disse|minhas|"
    r"memoria|preferencia|nome|morada|trabalho|universidade|"
    r"segundo|segundos|data|versao|instalacao|estado)\b", re.I,
)


@dataclass(frozen=True)
class Route:
    use_context: bool
    reason: str


class PerformanceEngine:
    """Maintains constant-memory aggregates, without retaining user content."""

    def __init__(self, profile: str = "balanced", *, clock=perf_counter, samples: int = 96):
        if profile not in {"balanced", "legacy"}:
            raise ValueError("AURA_PERFORMANCE_PROFILE must be balanced or legacy")
        if not 16 <= samples <= 512:
            raise ValueError("Invalid performance sampling bound")
        self.profile = profile
        self.clock = clock
        self._samples = deque(maxlen=samples)
        self._requests = 0
        self._context_skips = 0
        self._errors = 0

    def route(self, question: str, history: list[dict] | None = None) -> Route:
        if self.profile != "legacy" or history:
            return Route(True, "full_context")
        if not isinstance(question, str) or len(question) > 120:
            return Route(True, "full_context")
        normalized = _fold(question.strip())
        if _CONTEXT.search(normalized):
            return Route(True, "contextual_question")
        match = _GENERAL.fullmatch(normalized)
        if not match:
            return Route(True, "unclassified_question")
        # Multi-part requests require the memory/research path, even if the
        # opening resembles a definition. The "e" in "o que e" is excluded
        # by inspecting only the subject captured after the introductory verb.
        topic = normalized
        for opener in ("o que e ", "o que sao ", "define ",
                       "explica o que e ", "explica o conceito de ",
                       "qual e a definicao de ", "qual a definicao de ",
                       "qual e o significado de ", "qual o significado de "):
            if topic.startswith(opener):
                topic = topic[len(opener):]
                break
        if re.search(r"\\b(?:e|mas|porque|como|quando|onde|devo|posso|"
                     r"quero|preciso|mim|comigo|ti|contigo|me|nos|"
                     r"fazer|escolher)\\b", topic):
            return Route(True, "multi_part_question")
        return Route(False, "general_definition")

    def record(self, *, route: Route, prepare_ms: float,
               total_ms: float, first_token_ms: float | None,
               error: bool = False) -> None:
        values = (prepare_ms, total_ms)
        if (any(not math.isfinite(v) or v < 0 for v in values) or
                first_token_ms is not None and
                (not math.isfinite(first_token_ms) or first_token_ms < 0)):
            return
        self._requests += 1
        if not route.use_context:
            self._context_skips += 1
        if error:
            self._errors += 1
        self._samples.append((prepare_ms, total_ms, first_token_ms))

    @staticmethod
    def _percentile(values: list[float], quantile: float):
        if not values:
            return None
        ordered = sorted(values)
        index = math.ceil(quantile * len(ordered)) - 1
        return round(ordered[max(index, 0)], 2)

    def status(self) -> dict:
        samples = list(self._samples)
        def summary(index: int) -> dict:
            values = [row[index] for row in samples if row[index] is not None]
            return {"p50_ms": round(median(values), 2) if values else None,
                    "p95_ms": self._percentile(values, 0.95)}
        return {
            "version": "4.0",
            "profile": self.profile,
            "requests": self._requests,
            "errors": self._errors,
            "context_skips": self._context_skips,
            "sample_count": len(samples),
            "max_samples": self._samples.maxlen,
            "context_preparation": summary(0),
            "request_total": summary(1),
            "first_visible_token": summary(2),
            "first_token_requires_streaming": True,
            "private_text_stored": False,
            "hardware_performance_measured": False,
        }
