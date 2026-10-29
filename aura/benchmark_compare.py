"""Compare real Ollama benchmark reports without modifying model settings.

Usage: python -m aura.benchmark_compare before.json after.json
A PASS only checks comparable measurements, never proves answer quality.
"""
import argparse
import json
import math
from pathlib import Path


METRICS = ("elapsed_ms", "total_ms", "generation_ms", "tokens_per_second")


def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def compare(baseline, candidate, *, max_regression_pct=5.0):
    """Fail closed when reports lack comparable metadata or enough samples."""
    if not 0 <= max_regression_pct <= 100:
        raise ValueError("Invalid regression threshold")
    fields = ("model", "url", "streaming", "python", "platform")
    for field in fields:
        if field not in baseline or baseline.get(field) != candidate.get(field):
            return {"decision": "inconclusive", "reason": "missing or different " + field}
    for report in (baseline, candidate):
        runs = report.get("runs")
        samples = report.get("samples")
        if type(runs) is not int or runs < 10 or not isinstance(samples, list) or len(samples) != runs:
            return {"decision": "inconclusive", "reason": "at least 10 complete runs required"}
        if not isinstance(report.get("summary"), dict):
            return {"decision": "inconclusive", "reason": "missing summary"}
    metrics = {}
    for metric in METRICS:
        before = baseline["summary"].get(metric, {})
        after = candidate["summary"].get(metric, {})
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        p50a, p50b = before.get("p50"), after.get("p50")
        p95a, p95b = before.get("p95"), after.get("p95")
        if not all(_finite_positive(v) for v in (p50a, p50b, p95a, p95b)):
            continue
        if before.get("samples") != baseline["runs"] or after.get("samples") != candidate["runs"]:
            continue
        direction = 1 if metric == "tokens_per_second" else -1
        change = round(100 * (p95b / p95a - 1), 3)
        regression = (-direction * change) > max_regression_pct
        metrics[metric] = {"before_p50": p50a, "after_p50": p50b,
                           "before_p95": p95a, "after_p95": p95b,
                           "p95_change_pct": change, "regression": regression}
    if "elapsed_ms" not in metrics:
        return {"decision": "inconclusive", "reason": "missing valid elapsed_ms samples",
                "metrics": metrics}
    if any(item["regression"] for item in metrics.values()):
        decision = "reject"
    elif metrics["elapsed_ms"]["after_p50"] < metrics["elapsed_ms"]["before_p50"] and metrics["elapsed_ms"]["after_p95"] < metrics["elapsed_ms"]["before_p95"]:
        decision = "candidate_for_review"
    else:
        decision = "inconclusive"
    return {"decision": decision, "metrics": metrics,
            "limitations": ["No quality or correctness comparison",
                            "Hardware load and model version must be controlled externally",
                            "Approval and merge require human review"]}


def main():
    parser = argparse.ArgumentParser(description="Compare measured Ollama benchmark JSON files")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-regression-pct", type=float, default=5.0)
    args = parser.parse_args()
    first = json.loads(args.baseline.read_text(encoding="utf-8"))
    second = json.loads(args.candidate.read_text(encoding="utf-8"))
    print(json.dumps(compare(first, second, max_regression_pct=args.max_regression_pct),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
