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
            if len(line) > max_chars * 2:
                raise ValueError("Ollama event too large")
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Invalid Ollama event")
            if event.get("error"):
                raise ValueError("Ollama stream returned an error")
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
    def duration_ms(key):
        ns = terminal.get(key)
        return round(ns / 1_000_000, 3) if type(ns) is int and ns >= 0 else None
    tokens = terminal.get("eval_count")
    if type(tokens) is not int or tokens < 0:
        tokens = None
    eval_ns = terminal.get("eval_duration")
    return decoded, {
        "total_ms": duration_ms("total_duration"),
        "load_ms": duration_ms("load_duration"),
        "prompt_eval_ms": duration_ms("prompt_eval_duration"),
        "generation_ms": duration_ms("eval_duration"),
        "generated_tokens": tokens,
        "tokens_per_second": (round(tokens * 1_000_000_000 / eval_ns, 2)
                              if tokens is not None and type(eval_ns) is int and eval_ns > 0 else None),
        "ttft_ms": round((first-started)/1_000_000, 3) if first else None,
        "elapsed_ms": round((time.perf_counter_ns()-started)/1_000_000, 3),
    }
