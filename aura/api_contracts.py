"""Fail fast on ambiguous API route registrations.

FastAPI/Starlette allow identical route declarations and will dispatch to
the first match, silently masking later handlers. This guard keeps the
public API unambiguous without changing HTTP behavior.
"""
from __future__ import annotations

from collections import defaultdict
from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute


def validate_api_routes(app) -> dict:
    entries: dict[tuple[str, str], list[str]] = defaultdict(list)
    count = 0
    for route in app.routes:
        if isinstance(route, APIRoute):
            count += 1
            for method in route.methods or ():
                entries[(method, route.path)].append(route.name)
        elif isinstance(route, WebSocketRoute):
            count += 1
            entries[("WEBSOCKET", route.path)].append(route.name)
    duplicates = {
        f"{method} {path}": names
        for (method, path), names in entries.items() if len(names) > 1
    }
    if duplicates:
        detail = ", ".join(f"{key}: {names}" for key, names in sorted(duplicates.items()))
        raise RuntimeError(f"Rotas API duplicadas: {detail}")
    return {"routes_checked": count, "duplicates": 0}
