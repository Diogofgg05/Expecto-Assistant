"""Fail closed on malformed or incomplete laboratory evidence."""
import math


def validate_report(report):
    if not isinstance(report, dict) or report.get('complete') is not True:
        raise ValueError('A complete report object is required')
    for key, lower, upper in [('repeats',1,10),('case_count',1,700),('warmup',0,3)]:
        value = report.get(key)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f'Invalid {key}')
    if not isinstance(report.get('corpus_sha256'), str) or len(report['corpus_sha256']) != 64:
        raise ValueError('Missing corpus fingerprint')
    rows = report.get('rows')
    if not isinstance(rows, list) or not rows or len(rows) > 42000:
        raise ValueError('Invalid trial list')
    indexed, groups, domains = {}, {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid trial')
        case, repeat, profile, pipeline = (row.get(k) for k in ('case_id','repeat','profile','pipeline'))
        if not isinstance(case,str) or not case or len(case)>100 or type(repeat) is not int or not 0 <= repeat < report['repeats']:
            raise ValueError('Invalid case or repetition')
        if profile not in ('eco','balanced','max') or pipeline not in ('raw','reviewed'):
            raise ValueError('Unknown profile or pipeline')
        if row.get('effective_profile') not in ('eco','balanced','max','pressure_override'):
            raise ValueError('Unknown effective profile')
        if any(type(row.get(k)) is not bool for k in ('ok','correct')) or row['correct'] and not row['ok']:
            raise ValueError('Invalid correctness or success flag')
        latency = row.get('total_ms')
        if type(latency) not in (int,float) or not math.isfinite(latency) or latency <= 0:
            raise ValueError('Invalid latency')
        domain = row.get('domain')
        if domain not in ('math','programming','research') or case in domains and domains[case] != domain:
            raise ValueError('Invalid or inconsistent domain')
        domains[case] = domain
        key = (case,repeat,profile,pipeline)
        if key in indexed:
            raise ValueError('Duplicate trial')
        indexed[key] = row
        groups.setdefault((profile,pipeline),set()).add((case,repeat))
    expected = {(case,r) for case in domains for r in range(report['repeats'])}
    pipelines = {p for _,p in groups}
    if len(domains) != report['case_count'] or 'raw' not in pipelines:
        raise ValueError('Missing cases or raw baseline')
    if set(groups) != {(mode,p) for mode in ('eco','balanced','max') for p in pipelines}:
        raise ValueError('Missing profile group')
    if any(keys != expected for keys in groups.values()):
        raise ValueError('Incomplete trial coverage despite complete flag')
    return indexed
