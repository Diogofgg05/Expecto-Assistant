"""Opt-in local A/B measurement for Ollama context sizes. Does not change app config.

Example: python -m aura.ollama_tuning_lab --model qwen3 --baseline-ctx 8192 --candidate-ctx 4096 --runs 20 --output tuning.json

This is a bounded performance/smoke-quality experiment, not general model evaluation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .benchmark_identity import collect_identity
from .ollama_benchmark import percentile

# Short, deterministic sanity tasks; they do not prove general answer quality.
PROBES = (("Calcula 7 + 5. Responde apenas JSON com o campo answer.", "12"),
          ("Calcula 9 * 3. Responde apenas JSON com o campo answer.", "27"),
          ("Calcula 100 - 42. Responde apenas JSON com o campo answer.", "58"))


def _loopback_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or not parsed.port or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Ollama must be a local HTTP loopback URL with port")
    return url.rstrip("/")


async def _measure(client, url, model, ctx, probe):
    question, expected = probe
    started = time.perf_counter_ns()
    try:
        response = await client.post(url + "/api/chat", json={
            "model": model, "stream": False, "format": "json", "keep_alive": "5m",
            "options": {"temperature": 0, "num_predict": 96, "num_ctx": ctx},
            "messages": [{"role": "user", "content": question}],
        })
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Invalid Ollama message")
        answer = json.loads(message["content"])
        correct = isinstance(answer, dict) and str(answer.get("answer", "")).strip() == expected
        ns = payload.get("eval_duration")
        tokens = payload.get("eval_count")
        rate = (round(tokens * 1_000_000_000 / ns, 2)
                if type(tokens) is int and tokens >= 0 and type(ns) is int and ns > 0 else None)
        return {"elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
                "correct": correct, "tokens_per_second": rate, "error": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
                "correct": False, "tokens_per_second": None, "error": type(exc).__name__}


def _summary(rows):
    values = [row["elapsed_ms"] for row in rows]
    rates = [row["tokens_per_second"] for row in rows if row["tokens_per_second"] is not None]
    return {"runs": len(rows), "correct": sum(row["correct"] for row in rows),
            "errors": sum(row["error"] is not None for row in rows),
            "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95),
            "tokens_per_second_p50": percentile(rates, 50)}


def _decision(base, candidate, min_gain_pct):
    if base["correct"] != base["runs"] or base["errors"]:
        return "inconclusive", "baseline did not pass all sanity probes"
    if candidate["correct"] != candidate["runs"] or candidate["errors"]:
        return "reject", "candidate failed a sanity probe or request"
    faster_p50 = candidate["p50_ms"] < base["p50_ms"]
    p95_gain = 100 * (base["p95_ms"] - candidate["p95_ms"]) / base["p95_ms"]
    if faster_p50 and p95_gain >= min_gain_pct:
        return "candidate_for_review", "measured p95 improved; full quality review required"
    return "inconclusive", "no repeatable gain established by this small experiment"


async def tune(model, url="http://127.0.0.1:11434", *, baseline_ctx=8192,
               candidate_ctx=4096, runs=20, warmup=2, min_gain_pct=5.0):
    url = _loopback_url(url)
    if not (isinstance(model, str) and model.strip() and len(model) <= 120):
        raise ValueError("Invalid Ollama model")
    if any(type(ctx) is not int or ctx < 1024 or ctx > 8192 for ctx in (baseline_ctx, candidate_ctx)):
        raise ValueError("Context sizes must be between 1024 and 8192")
    if baseline_ctx == candidate_ctx:
        raise ValueError("Candidate must differ from baseline")
    if (type(runs) is not int or not 10 <= runs <= 100
            or type(warmup) is not int or not 0 <= warmup <= 5
            or type(min_gain_pct) not in (int, float) or not math.isfinite(min_gain_pct)
            or not 0 < min_gain_pct <= 50):
        raise ValueError("Invalid experiment bounds")
    identity = await collect_identity(url, model)
    results = {"baseline": [], "candidate": []}
    contexts = {"baseline": baseline_ctx, "candidate": candidate_ctx}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3),
                                 follow_redirects=False, trust_env=False) as client:
        for index in range(runs + warmup):
            # Alternate pair ordering to reduce systematic warm/cold and drift bias.
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            probe = PROBES[index % len(PROBES)]
            for name in order:
                sample = await _measure(client, url, model, contexts[name], probe)
                if index >= warmup:
                    results[name].append(sample)
    base, cand = _summary(results["baseline"]), _summary(results["candidate"])
    decision, reason = _decision(base, cand, min_gain_pct)
    return {**identity, "model": model, "url": url,
            "settings": {"baseline_num_ctx": baseline_ctx, "candidate_num_ctx": candidate_ctx,
                         "temperature": 0, "num_predict": 96, "keep_alive": "5m"},
            "runs": runs, "warmup": warmup, "baseline": base, "candidate": cand,
            "decision": decision, "reason": reason,
            "limitations": ["Only three simple arithmetic probes; not a full reasoning evaluation",
                            "System load, model runtime and thermal conditions not controlled",
                            "No production configuration changes were made"]}


def main():
    parser = argparse.ArgumentParser(description="Local A/B Ollama context experiment")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--baseline-ctx", type=int, default=8192)
    parser.add_argument("--candidate-ctx", type=int, default=4096)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--min-gain-pct", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(tune(args.model, args.url, baseline_ctx=args.baseline_ctx,
                              candidate_ctx=args.candidate_ctx, runs=args.runs,
                              warmup=args.warmup, min_gain_pct=args.min_gain_pct))
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
