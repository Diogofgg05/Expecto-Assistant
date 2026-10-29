"""Lightweight, loop-owned HTTP connection reuse for local Ollama inference.

One on-demand pool per Ollama instance. No daemon, credentials, user prompts,
remote fallback or unbounded connection growth. Close it on FastAPI shutdown.
"""
from __future__ import annotations

import asyncio
import httpx


class LocalInferencePool:
    """Reuse keep-alive connections inside one running event loop."""

    def __init__(self, *, max_connections: int = 2):
        if not 1 <= max_connections <= 8:
            raise ValueError("Invalid local Ollama connection limit")
        self.max_connections = max_connections
        self._client = None
        self._loop = None
        self.created = 0

    async def client(self):
        loop = asyncio.get_running_loop()
        if self._client is not None:
            if self._loop is loop and not getattr(self._client, "is_closed", False):
                return self._client
            await self.aclose()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(65.0, connect=3.0),
            limits=httpx.Limits(max_connections=self.max_connections,
                                max_keepalive_connections=self.max_connections,
                                keepalive_expiry=30.0),
            trust_env=False,
        )
        self._loop = loop
        self.created += 1
        return self._client

    async def aclose(self) -> None:
        old, self._client = self._client, None
        self._loop = None
        if old is not None:
            close = getattr(old, "aclose", None)
            if close is not None:
                await close()

    def status(self) -> dict:
        return {
            "created": self.created,
            "active": self._client is not None and
                      not getattr(self._client, "is_closed", False),
            "max_connections": self.max_connections,
            "private_content_stored": False,
        }
