"""Compare complete paired experiments without disguising quality regressions."""
import math
import statistics


def compare_reports(baseline, candidate):
    if baseline.get('environment') != candidate.get('environment'):
        raise ValueError('Environment differs or is missing in one report')
    for key in ('corpus_sha256', 'repeats', 'warmup'):
        if not baseline.get(key) or baseline.get(key) != candidate.get(key):
            if key == 'warmup' and baseline.get(key) == candidate.get(key) == 0:
                continue
            raise ValueError(f'Incompatible or missing {key}')
    if not baseline.get('complete') or not candidate.get('complete'):
        raise ValueError('Both reports must be complete')
    def index(report):
        result = {}
        for row in report['rows']:
            key = (row['case_id'], row['repeat'], row['profile'], row['pipeline'])
            if key in result:
                raise ValueError('Duplicate trial')
            if not isinstance(row.get('total_ms'), (int, float)) or not math.isfinite(row['total_ms']) or row['total_ms'] <= 0:
                raise ValueError('Invalid latency')
            result[key] = row
        return result
    old, new = index(baseline), index(candidate)
    if not old or old.keys() != new.keys():
        raise ValueError('Trial coverage differs')
    groups = {}
    for key, row in new.items():
        groups.setdefault(key[2:], []).append((old[key], row))
    results = []
    for (profile, pipeline), pairs in sorted(groups.items()):
        losses = sum(bool(a['correct']) and not b['correct'] for a, b in pairs)
        failed = sum(not b['ok'] or b['effective_profile'] != profile for _, b in pairs)
        before = statistics.median(a['total_ms'] for a, _ in pairs)
        after = statistics.median(b['total_ms'] for _, b in pairs)
        results.append({'profile': profile, 'pipeline': pipeline,
            'baseline_median_ms': before, 'candidate_median_ms': after,
            'latency_change_pct': (after/before-1)*100,
            'paired_accuracy_losses': losses, 'failed_or_overridden': failed,
            'baseline_accuracy': sum(a['correct'] for a, _ in pairs)/len(pairs),
            'candidate_accuracy': sum(b['correct'] for _, b in pairs)/len(pairs),
            'observed_improvement_without_paired_loss': after < before and not losses and not failed
                and all(a['ok'] and a['effective_profile'] == profile for a, _ in pairs)})
    return {'comparisons': results, 'settings_changed': False,
            'limitation': 'Observed on this corpus only; use a new seed holdout before adopting changes. Hardware and background load must be comparable.'}
