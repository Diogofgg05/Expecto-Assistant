"""Ultra Performance Engine 6.0: conservative routing, context bounds and metrics.

No caches of private user prompts or responses. Profiling remains in RAM only.
Fast retrieval bypass is limited to self-contained general definitions.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import re
import statistics


@dataclass(frozen=True)
class Profile:
    name: str
    max_predict: int
    context_limit: int
    retrieve_personal: bool = True


FAST = Profile('fast', 160, 0, False)
STANDARD = Profile('standard', 450, 16000, True)
DEEP = Profile('deep', 700, 24000, True)

# Restrictive: changes only how a model receives context, not permission,
# system safety instructions, or application tool routing.
_FAST_PATTERN = re.compile(
    r'^(?:o que (?:é|e|significa)|define|explica brevemente o que é|qual a diferença entre)\s+',
    re.I,
)
_PERSONAL = re.compile(
    r'\b(?:meu|minha|meus|minhas|nosso|nossa|nossos|nossas|'
    r'lembras|lembraste|memória|memoria|dissemos|falámos|conversa|'
    r'expecto|aura|projeto|ficheiro|documento|pdf|repositório|github)\b',
    re.I,
)
_REFERENCE = re.compile(
    r'\b(?:isso|isto|esse|essa|aquele|anterior|acima|agora|também|então|assim|'
    r'último|última|esta resposta|continuar|continua)\b', re.I
)
_DEEP = re.compile(
    r'\b(?:demonstra|demonstre|passo a passo|código|codigo|programa|'
    r'depura|debug|algoritmo|complexidade|matriz|matrizes|'
    r'derivada|integral|equação|equacao|compara|prova que|'
    r'arquitetura|segurança|seguranca|auditoria|otimiza|raciocínio|raciocinio)\b',
    re.I
)
_CURRENT = re.compile(
    r'\b(?:hoje|atual|atuais|agora|202[0-9]|preço|preco|notícia|noticia|'
    r'presidente|eleições|eleicoes|legislação|legislacao)\b', re.I
)


def choose_profile(question: str, history=None, *, mode: str = 'balanced') -> Profile:
    """Route only self-contained *general* definitions to the lean path."""
    question = (question or '').strip()
    if mode == 'off':
        return STANDARD
    if mode not in ('balanced', 'conservative'):
        mode = 'conservative'
    if mode == 'balanced' and _DEEP.search(question):
        return DEEP
    if (mode == 'balanced' and 6 <= len(question) <= 135 and
            _FAST_PATTERN.match(question) and not _PERSONAL.search(question) and
            not _REFERENCE.search(question) and not _DEEP.search(question) and
            not _CURRENT.search(question)):
        return FAST
    return STANDARD


def bound_context(value: str, limit: int) -> str:
    """Restrict retrieved material, never the immutable system safety prompt."""
    if not value or not limit or len(value) <= limit:
        return value
    # Preserve full lines to avoid dangling URLs or half claims.
    excerpt = value[:max(0, limit - 96)]
    last = excerpt.rfind('\n')
    if last > limit // 2:
        excerpt = excerpt[:last]
    return excerpt + '\n[Contexto secundário truncado por limite de processamento.]'


class PerformanceMonitor:
    """Bounded in-memory telemetry without prompts, responses or personal data."""

    def __init__(self):
        self._rows = deque(maxlen=64)

    def record(self, *, profile: str, prep_ms: float, total_ms: float,
               ttft_ms: float | None, context_chars: int, ok: bool):
        self._rows.append({
            'profile': profile, 'prep_ms': round(max(0, prep_ms), 1),
            'total_ms': round(max(0, total_ms), 1),
            'ttft_ms': round(ttft_ms, 1) if ttft_ms is not None else None,
            'context_chars': max(0, context_chars),
            'ok': bool(ok),
        })

    def summary(self) -> dict:
        rows = list(self._rows)
        def distribution(key: str):
            values = sorted(float(row[key]) for row in rows if row[key] is not None)
            if not values:
                return {'median': None, 'p95': None}
            from math import ceil
            return {'median': round(statistics.median(values), 1),
                    'p95': round(values[ceil(0.95 * len(values)) - 1], 1)}
        return {
            'sample_count': len(rows),
            'capacity': 64,
            'profile_counts': dict(Counter(row['profile'] for row in rows)),
            'failed_requests': sum(not row['ok'] for row in rows),
            'latency_ms': {
                'preparation': distribution('prep_ms'),
                'total': distribution('total_ms'),
                'first_token': distribution('ttft_ms'),
            },
            'mean_context_chars': round(statistics.mean(row['context_chars'] for row in rows))
                if rows else None,
            'stores_user_content': False,
        }
