"""In-process chiplet fabric: lazy, bounded service lifecycle, no extra workers.

Services share the existing database and event loop; creating subprocesses for
small services would increase RAM, context switches and IPC overhead. Calls to
``get`` initialise at most once, even when threads arrive concurrently.
"""
from __future__ import annotations

from threading import RLock
from time import perf_counter_ns
from typing import Callable


class ChipletFabric:
    """Lazily materialise registered services and expose safe lifecycle metrics.

    Service factories are trusted application code, not model-generated imports.
    Failed factories are retried on the next explicit access and never cached.
    """

    def __init__(self, factories: dict[str, Callable[[], object]]):
        if not factories or any(not name.isidentifier() or not callable(factory)
                                for name, factory in factories.items()):
            raise ValueError('Invalid chiplet registry')
        self._factories = dict(factories)
        self._instances: dict[str, object] = {}
        self._initialising: set[str] = set()
        self._calls: dict[str, int] = dict.fromkeys(factories, 0)
        self._failures: dict[str, int] = dict.fromkeys(factories, 0)
        self._cold_start_ns: dict[str, int] = {}
        self._lock = RLock()

    def get(self, name: str) -> object:
        """Use the shared service; nested dependencies use a reentrant lock."""
        if name not in self._factories:
            raise AttributeError(f'Unknown chiplet: {name}')
        with self._lock:
            self._calls[name] += 1
            if name in self._instances:
                return self._instances[name]
            if name in self._initialising:
                raise RuntimeError(f'Circular chiplet dependency: {name}')
            self._initialising.add(name)
            started = perf_counter_ns()
            try:
                instance = self._factories[name]()
                if instance is None:
                    raise RuntimeError(f'Chiplet factory returned None: {name}')
                self._instances[name] = instance
                self._cold_start_ns[name] = perf_counter_ns() - started
                return instance
            except Exception:
                self._failures[name] += 1
                raise
            finally:
                self._initialising.remove(name)

    def snapshot(self) -> dict:
        """Metrics without activating standby services or disclosing content."""
        with self._lock:
            active = sorted(self._instances)
            return {
                'architecture': 'in-process-lazy-chiplets',
                'total': len(self._factories),
                'active_count': len(active),
                'active': active,
                'standby': sorted(set(self._factories) - set(active)),
                'calls': dict(self._calls),
                'failures': dict(self._failures),
                'cold_start_ms': {
                    name: round(ns / 1_000_000, 3)
                    for name, ns in self._cold_start_ns.items()
                },
            }
