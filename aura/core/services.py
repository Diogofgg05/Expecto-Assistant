"""Per-engine service container with explicit, lazy replacement points.

Providers are configured only by trusted Python code, never by model text.
Importing this module does not load Ollama, speech engines or research clients.
Each container shares exactly one instance per registered service.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

# Builder dependencies flow in one direction: service container -> adapters.
# The adapter modules do not import CoreServices.
ServiceFactory = Callable[["CoreServices"], Any]


def _memory(c: "CoreServices"):
    from ..memory import MemoryEngine
    return MemoryEngine(c.settings, c.db)


def _llm(c: "CoreServices"):
    from ..llm import Ollama
    return Ollama(c.settings, c.db, c.get("memory"))


def _research(c: "CoreServices"):
    from ..research import Researcher
    return Researcher(c.db, c.settings.searxng_url)


def _extractor(c: "CoreServices"):
    from ..cognition import KnowledgeExtractor
    return KnowledgeExtractor(c.settings, c.db)


def _relations(c: "CoreServices"):
    from ..relations import RelationMemory
    return RelationMemory(c.db)


def _consolidation(c: "CoreServices"):
    from ..consolidation import ConsolidationEngine
    return ConsolidationEngine(c.db)


def _learning(c: "CoreServices"):
    from ..learning import LearningEngine
    return LearningEngine(c.settings, c.db)


def _optimizer(c: "CoreServices"):
    from ..optimizer import OptimizationLab
    return OptimizationLab(c.settings, c.db)


def _epistemics(c: "CoreServices"):
    from ..epistemics import EpistemicEngine
    return EpistemicEngine(c.db)


def _quality(c: "CoreServices"):
    from ..quality import KnowledgeQuality
    return KnowledgeQuality(c.db)


def _factcheck(c: "CoreServices"):
    from ..factcheck import FactChecker
    return FactChecker(c.db)


def _continuity(c: "CoreServices"):
    from ..living_intelligence import ContinuityEngine
    return ContinuityEngine(c.db)


def _reflection(c: "CoreServices"):
    from ..reflection import ReflectionEngine
    return ReflectionEngine(c.db)


def _secure_backups(c: "CoreServices"):
    from ..security import SecureBackupManager
    return SecureBackupManager(c.db, c.settings.data_dir / "secure_backups", c.settings.backup_passphrase)


DEFAULT_FACTORIES: Mapping[str, ServiceFactory] = {
    "memory": _memory,
    "llm": _llm,
    "research": _research,
    "extractor": _extractor,
    "relations": _relations,
    "consolidation": _consolidation,
    "learning": _learning,
    "optimizer": _optimizer,
    "epistemics": _epistemics,
    "quality": _quality,
    "factcheck": _factcheck,
    "continuity": _continuity,
    "reflection": _reflection,
    "secure_backups": _secure_backups,
}


class CoreServices:
    """Scoped factories, not a global singleton or user-configurable plugin API.

    Injection is explicit and in-process; no remote configuration can activate
    a service or grant model-generated text permission to call it.
    """

    def __init__(self, settings, db, *, factories: Mapping[str, ServiceFactory] | None = None):
        self.settings = settings
        self.db = db
        override = dict(factories or {})
        unknown = override.keys() - DEFAULT_FACTORIES.keys()
        if unknown:
            raise ValueError("Dependências desconhecidas: " + ", ".join(sorted(unknown)))
        if any(not callable(factory) for factory in override.values()):
            raise TypeError("Cada fábrica de serviço tem de ser chamável.")
        self._factories = dict(DEFAULT_FACTORIES)
        self._factories.update(override)
        self._instances: dict[str, Any] = {}
        self._constructing: set[str] = set()

    @property
    def initialized(self) -> frozenset[str]:
        """Service names only; never exposes stored memories or credentials."""
        return frozenset(self._instances)

    def get(self, name: str):
        if name not in self._factories:
            raise KeyError(name)
        if name in self._instances:
            return self._instances[name]
        if name in self._constructing:
            raise RuntimeError("Dependência circular no serviço: " + name)
        self._constructing.add(name)
        try:
            instance = self._factories[name](self)
            if instance is None:
                raise TypeError("A fábrica não pode devolver None: " + name)
            self._instances[name] = instance
            return instance
        finally:
            self._constructing.remove(name)
