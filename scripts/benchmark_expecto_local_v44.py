"""Measure actual Expecto -> Ollama SSE latency on the user's own localhost.

Does not log response text or private prompts; uses only built-in synthetic
questions. Refuses to benchmark while automatic conversation recording is on.
This measures the installed/running version, NOT necessarily the GitHub HEAD.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter
from urllib.parse import urlparse

import httpx


PROMPTS = (
    ("cpu", "Explica em quatro frases o funcionamento básico de uma CPU."),
    ("matrices", "Explica porque duas matrizes invertíveis podem ter uma soma singular."),
)


def local_url(value: str) -> str:
    parsed = urlparse(value)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")
            or parsed.port is None or not 1 <= parsed.port <= 65535):
        raise ValueError("Benchmark only accepts http://127.0.0.1:PORT or http://localhost:PORT")
    return f"http://{parsed.hostname}:{parsed.port}"


def percentile(values: list[float], q: float):
    if not values:
        return None
    rows = sorted(values)
    return round(rows[max(0, math.ceil(q * len(rows)) - 1)], 3)


def summary(values: list[float]):
    return {
        "samples": len(values),
        "p50_ms": round(median(values), 3) if values else None,
        "p95_ms": percentile(values, 0.95),
    }


def parse_sse_lines(lines, now=perf_counter):
    """Consume SSE frames; never return or store generated token contents."""
    started = now()
    first = None
    final = None
    draft_chars = 0
    for line in lines:
        if not line.startswith("data: "):
            continue
        obj = json.loads(line[6:])
        if not isinstance(obj, dict):
            raise ValueError("Invalid SSE frame")
        kind = obj.get("type")
        if kind == "error":
            raise RuntimeError("Expecto streaming returned an error")
        if kind == "token":
            token = obj.get("text", "")
            if not isinstance(token, str):
                raise ValueError("Malformed token frame")
            draft_chars += len(token)
            if first is None and token:
                first = (now() - started) * 1000
        if kind == "final":
            payload = obj.get("payload")
            if not isinstance(payload, dict) or not payload.get("ok"):
                raise RuntimeError("Invalid final response")
            final = (now() - started) * 1000
    if final is None:
        raise RuntimeError("Missing verified final response")
    return {
        "first_token_ms": round(first, 3) if first is not None else None,
        "final_ms": round(final, 3),
        "draft_char_count": draft_chars,
    }


def benchmark(base_url: str, label: str, runs: int, warmups: int):
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=3.0),
                      trust_env=False) as client:
        status = client.get(base_url + "/api/memory/status")
        status.raise_for_status()
        memory = status.json()
        if memory.get("recording") is not False and memory.get("private_mode") is not True:
            raise RuntimeError(
                "Conversation recording is enabled. Run the backend with "
                "AURA_EPISODIC_CAPTURE=false or enable private mode before "
                "benchmarking, and verify /api/memory/status."
            )
        compute = client.get(base_url + "/api/compute/status")
        compute.raise_for_status()
        compute_data = compute.json()
        policy = compute_data.get("policy", {})
        model = policy.get("primary_model")
        profile = compute_data.get("performance", {}).get("profile")

        def one_case(prompt):
            request = {"message": prompt, "history": [],
                       "session_id": "benchmark-local-v44"}
            with client.stream("POST", base_url + "/api/command/stream",
                               json=request) as response:
                response.raise_for_status()
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise RuntimeError("SSE streaming not available")
                return parse_sse_lines(response.iter_lines())

        cases = {}
        for case_id, question in PROMPTS:
            for _ in range(warmups):
                one_case(question)
            values = [one_case(question) for _ in range(runs)]
            cases[case_id] = {
                "first_token": summary(
                    [v["first_token_ms"] for v in values
                     if v["first_token_ms"] is not None]),
                "verified_final": summary([v["final_ms"] for v in values]),
                "no_draft_tokens": sum(
                    v["first_token_ms"] is None for v in values),
            }
        return {
            "schema": "expecto-real-local-v44",
            "label": label,
            "model": model,
            "compute_profile": policy.get("profile"),
            "performance_profile": profile,
            "runs_per_prompt": runs,
            "warmups_per_prompt": warmups,
            "prompt_ids": [case_id for case_id, _ in PROMPTS],
            "cases": cases,
            "saved_private_text": False,
            "actual_ollama_used": True,
            "limitations": (
                "Measures localhost Expecto SSE, including backend review and "
                "transport overhead. Draft tokens may be revised in the final "
                "answer; model weights, hardware and settings must match A/B."
            ),
        }


def compare(old: dict, new: dict):
    for key in ("schema", "model", "prompt_ids"):
        if old.get(key) != new.get(key):
            raise ValueError(f"Reports cannot be compared: {key} differs")
    print("Experiência local — before / after")
    print("Ratios apply only to verified-final SSE latency; lower is better.")
    for prompt_id in old["prompt_ids"]:
        a = old["cases"][prompt_id]["verified_final"]["p50_ms"]
        b = new["cases"][prompt_id]["verified_final"]["p50_ms"]
        if a is None or b is None:
            raise ValueError("Missing timings")
        print(f"{prompt_id}: {a:.1f} ms -> {b:.1f} ms ({a / b:.2f}x)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--label", default="current")
    parser.add_argument("--output", type=Path, default=Path("expecto_local_benchmark.json"))
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"))
    args = parser.parse_args()
    if args.compare is not None:
        old, new = [json.loads(Path(path).read_text(encoding="utf-8"))
                    for path in args.compare]
        compare(old, new)
        return
    if not 1 <= args.runs <= 30 or not 0 <= args.warmups <= 4:
        parser.error("runs 1..30 and warmups 0..4 required")
    base = local_url(args.url)
    report = benchmark(base, args.label, args.runs, args.warmups)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n",
                           encoding="utf-8")
    for key, value in report["cases"].items():
        print(key, "first token:", value["first_token"],
              "verified final:", value["verified_final"])
    print("Ollama real: SIM. Resposta e perguntas privadas guardadas: NÃO.")
    print("Relatório:", args.output)


if __name__ == "__main__":
    main()
