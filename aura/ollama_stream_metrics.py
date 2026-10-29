"""Optional Ollama stream reader for timing first content and validating final JSON."""
import json
import time

import httpx


async def collect_json_stream(client, url, payload, *, max_chars=250000):
    """Return (decoded_json, timing_ms). Never return partial JSON."""
    started = time.perf_counter_ns()
    first = None
    chunks = []
    count = 0
    terminal = None
    async with client.stream("POST", url, json={**payload, "stream": True}) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Invalid Ollama event")
            message = event.get("message") or {}
            if not isinstance(message, dict):
                raise ValueError("Invalid Ollama message")
            fragment = message.get("content", "")
            if not isinstance(fragment, str):
                raise ValueError("Invalid Ollama fragment")
            if fragment:
                if first is None:
                    first = time.perf_counter_ns()
                count += len(fragment)
                if count > max_chars:
                    raise ValueError("Ollama output too large")
                chunks.append(fragment)
            if event.get("done") is True:
                terminal = event
                break
    if terminal is None:
        raise ValueError("Missing Ollama terminal event")
    decoded = json.loads("".join(chunks))
    if not isinstance(decoded, dict):
        raise ValueError("Expected JSON object")
    return decoded, {
        "ttft_ms": round((first-started)/1_000_000, 3) if first else None,
        "elapsed_ms": round((time.perf_counter_ns()-started)/1_000_000, 3),
    }
