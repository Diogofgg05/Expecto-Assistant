"""Held-out evaluation of simple vs layered reasoning, without self-grading by an LLM.

Scores lexical agreement, citation IDs and abstention only; they are NOT semantic proof.
Gold answers never enter prompts. One model/benchmark comparison is insufficient to
claim general improvement. No automatic model update or publishing happens here.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import unicodedata
from collections import defaultdict

MAX_CASES = 200


def _tokens(text):
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return set(re.findall(r"\b[a-z0-9]{2,}\b", normalized))


def _f1(answer, reference):
    a, b = _tokens(answer), _tokens(reference)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def _is_valid_case(case):
    if not isinstance(case, dict) or not all(k in case for k in ('id','question','reference','gold_evidence_ids','answerable')):
        raise ValueError('Missing benchmark fields')
    if not isinstance(case['answerable'], bool) or not isinstance(case['question'],str) or not case['question'].strip():
        raise ValueError('Invalid case question or answerability')
    if not isinstance(case['reference'],str) or not isinstance(case['gold_evidence_ids'], list):
        raise ValueError('Invalid gold references')
    if not all(isinstance(v,str) for v in case['gold_evidence_ids']):
        raise ValueError('Invalid reference IDs')
    if case['answerable'] and (not case['reference'].strip() or not case['gold_evidence_ids']):
        raise ValueError('Answerable cases need ground truth and evidence')
    if not case['answerable'] and case['gold_evidence_ids']:
        raise ValueError('Unanswerable cases should not require supporting evidence')


def validate_suite(suite):
    if not isinstance(suite,dict) or any(part not in suite for part in ('dev','test')):
        raise ValueError('Separate dev and test sets are required')
    ids=set()
    for partition in ('dev','test'):
        cases=suite[partition]
        if not isinstance(cases,list) or not cases or len(cases)>MAX_CASES:
            raise ValueError('A nonempty bounded suite is required')
        for case in cases:
            _is_valid_case(case)
            if not isinstance(case['id'],str) or not case['id'] or case['id'] in ids:
                raise ValueError('Case IDs must be unique across partitions')
            ids.add(case['id'])
    return hashlib.sha256(json.dumps(suite,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def grade_case(case, response):
    if not isinstance(response,dict):
        raise ValueError('Expected a structured answer')
    answer=response.get('answer','')
    ids=response.get('evidence_ids',[])
    abstained=response.get('abstained',False)
    if not isinstance(answer,str) or not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or not isinstance(abstained,bool):
        raise ValueError('Invalid answer schema')
    expected=set(case['gold_evidence_ids'])
    cited=set(ids)
    if not case['answerable']:
        passed=abstained and not answer.strip() and not cited
        return {'correct_abstention':passed,'f1':1.0 if passed else 0.0,'citation_recall':1.0 if passed else 0.0,'citation_precision':1.0 if passed else 0.0,'score':1.0 if passed else 0.0}
    f1=_f1(answer,case['reference']) if not abstained else 0.0
    recall=len(expected & cited)/len(expected)
    precision=len(expected & cited)/len(cited) if cited else 0.0
    # all components must be strong: good words without source is not success
    return {'correct_abstention':False,'f1':round(f1,4),'citation_recall':round(recall,4),'citation_precision':round(precision,4),'score':round(.5*f1+.3*recall+.2*precision,4)}


def _summarize(rows):
    return {'count':len(rows),'mean_score':round(sum(x['score'] for x in rows)/len(rows),4),
            'mean_f1':round(sum(x['f1'] for x in rows)/len(rows),4),
            'mean_citation_recall':round(sum(x['citation_recall'] for x in rows)/len(rows),4)}


async def compare_methods(suite, baseline, candidate, *, minimum_dev_gain=.03, maximum_test_drop=0.0):
    """Both async methods accept only question and return answer/evidence_ids/abstained.

    Candidate is recommended only if it improves dev and does not regress holdout.
    The holdout is evaluated once here; never use it to tune strategies repeatedly.
    """
    fingerprint=validate_suite(suite)
    results={}
    for partition in ('dev','test'):
        cases=suite[partition]
        results[partition]={}
        for name, fn in [('baseline',baseline),('candidate',candidate)]:
            rows=[]
            for case in cases:
                # Never pass case['reference'] or gold evidence IDs to the model.
                try:
                    response=await fn(case['question'])
                    graded=grade_case(case,response)
                except (ValueError,TypeError,KeyError,TimeoutError,asyncio.TimeoutError):
                    graded={'correct_abstention':False,'f1':0.0,'citation_recall':0.0,'citation_precision':0.0,'score':0.0}
                rows.append({'id':case['id'],**graded})
            results[partition][name]={'summary':_summarize(rows),'cases':rows}
    dev_gain=results['dev']['candidate']['summary']['mean_score']-results['dev']['baseline']['summary']['mean_score']
    test_gain=results['test']['candidate']['summary']['mean_score']-results['test']['baseline']['summary']['mean_score']
    recommended=dev_gain>=minimum_dev_gain and test_gain>=-maximum_test_drop
    return {'benchmark_sha256':fingerprint,'metrics':'surface_form_and_citation_not_semantic_truth',
            'results':results,'dev_gain':round(dev_gain,4),'test_gain':round(test_gain,4),
            'recommendation':'candidate_for_human_review' if recommended else 'retain_baseline',
            'limitations':['No semantic entailment verification','One holdout test does not establish generalization','Approval and deployment require manual review']}
