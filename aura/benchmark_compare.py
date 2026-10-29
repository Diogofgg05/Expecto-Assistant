"""Compare real Ollama benchmark reports without modifying model settings.

Usage: python -m aura.benchmark_compare before.json after.json
A PASS only checks comparable measurements, never proves answer quality.
"""
import argparse
import json
import math
from pathlib import Path


METRICS = ("elapsed_ms", "total_ms", "generation_ms", "tokens_per_second")


def percentile(values, pct):
    values = sorted(values)
    position = (len(values) - 1) * pct / 100
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 3)


def _extract(report, metric):
    values = [row.get(metric) for row in report['samples']]
    if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in values):
        return None
    return {'p50': percentile(values, 50), 'p95': percentile(values, 95)}


def compare(baseline, candidate, *, max_regression_pct=5.0):
    """Recalculate percentiles from observed samples, never trust cached summaries."""
    if type(max_regression_pct) not in (int, float) or not math.isfinite(max_regression_pct) or not 0 <= max_regression_pct <= 100:
        raise ValueError('Invalid regression threshold')
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return {'decision': 'inconclusive', 'reason': 'invalid reports'}
    for field in ('model', 'url', 'streaming', 'python', 'platform'):
        if field not in baseline or field not in candidate or baseline[field] != candidate[field]:
            return {'decision': 'inconclusive', 'reason': 'missing or different ' + field}
    # Benchmark v2: fail closed on legacy reports or mismatched model weights,
    # prompt, CPU and RAM. Comparing only model tags is not reproducible.
    import re
    if baseline.get('schema_version') != 2 or candidate.get('schema_version') != 2:
        return {'decision': 'inconclusive', 'reason': 'benchmark schema v2 required'}
    for field in ('model_digest', 'workload_sha256'):
        before, after = baseline.get(field), candidate.get(field)
        if not (isinstance(before, str) and re.fullmatch('[0-9a-f]{64}', before)
                and isinstance(after, str) and re.fullmatch('[0-9a-f]{64}', after)):
            return {'decision': 'inconclusive', 'reason': 'missing or invalid ' + field}
        if before != after:
            return {'decision': 'inconclusive', 'reason': 'different ' + field}
    hardware_keys = ('system', 'architecture', 'cpu_model', 'logical_cpus', 'physical_ram_bytes')
    for report in (baseline, candidate):
        h = report.get('hardware')
        if (not isinstance(h, dict) or not all(isinstance(h.get(k), str) and h[k].strip()
             for k in hardware_keys[:3]) or type(h.get('logical_cpus')) is not int
                or h['logical_cpus'] <= 0 or type(h.get('physical_ram_bytes')) is not int
                or h['physical_ram_bytes'] <= 0):
            return {'decision': 'inconclusive', 'reason': 'missing or invalid hardware profile'}
    if any(baseline['hardware'][k] != candidate['hardware'][k] for k in hardware_keys):
        return {'decision': 'inconclusive', 'reason': 'different hardware profile'}
    for report in (baseline, candidate):
        runs, samples = report.get('runs'), report.get('samples')
        if type(runs) is not int or runs < 10 or not isinstance(samples, list) or len(samples) != runs or any(not isinstance(row, dict) for row in samples):
            return {'decision': 'inconclusive', 'reason': 'at least 10 valid run samples required'}
    metrics = {}
    for key in METRICS:
        before, after = _extract(baseline, key), _extract(candidate, key)
        if before is None or after is None:
            continue
        change = round(100 * (after['p95'] / before['p95'] - 1), 3)
        regression = change < -max_regression_pct if key == 'tokens_per_second' else change > max_regression_pct
        metrics[key] = {'before_p50': before['p50'], 'after_p50': after['p50'],
                        'before_p95': before['p95'], 'after_p95': after['p95'],
                        'p95_change_pct': change, 'regression': regression}
    if 'elapsed_ms' not in metrics:
        return {'decision': 'inconclusive', 'reason': 'missing valid elapsed_ms samples', 'metrics': metrics}
    if any(m['regression'] for m in metrics.values()):
        decision = 'reject'
    elif metrics['elapsed_ms']['after_p50'] < metrics['elapsed_ms']['before_p50'] and metrics['elapsed_ms']['after_p95'] < metrics['elapsed_ms']['before_p95']:
        decision = 'candidate_for_review'
    else:
        decision = 'inconclusive'
    return {'decision': decision, 'metrics': metrics, 'limitations': [
        'Measured samples are recalculated; cached summary fields are not trusted',
        'Quality, hardware load and model runtime version not verified',
        'Human approval is required before merging']}


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
