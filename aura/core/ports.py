"""Small structural ports for replaceable inference and memory dependencies.

Interfaces describe *capabilities*, not particular libraries. The model never
receives a capability to invoke privileged tools; only the command router does.
"""
from __future__ import annotations

from typing import Any, AsyncContextManager, Protocol, runtime_checkable


@runtime_checkable
class ChatPort(Protocol):
    async def reply(self, question: str, history: list[dict] | None = None, *, on_token=None) -> str:
        ...

    async def health(self) -> dict:
        ...

    async def aclose(self) -> None:
        ...


@runtime_checkable
class MemoryPort(Protocol):
    async def recall(self, query: str, limit: int = 8) -> list[dict]:
        ...

    async def recall_episodes(self, query: str, months: int, limit: int = 5) -> list[dict]:
        ...

    def query_scope(self) -> AsyncContextManager[Any]:
        ...

    async def aclose(self) -> None:
        ...


@runtime_checkable
class ResearchPort(Protocol):
    async def learn(self, topic: str) -> Any:
        ...
