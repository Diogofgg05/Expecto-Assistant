"""Deterministic audit for generated claims. Flags risks, never certifies truth.

Avoids model-as-judge self-certification; exact citations and numbers are checked
against retrieved source text. Contradictions are *suspected*, not proven.
"""
from __future__ import annotations
import re
import unicodedata

_NUM = re.compile(r'(?<![\w])\d+(?:[.,]\d+)?(?!\w)')
_NEG = re.compile(r'\b(?:nao|nunca|jamais|sem|impossivel)\b')
_STOP = {'o','a','os','as','de','do','da','dos','das','em','no','na','um','uma','com','que','e','ou','se','para','por','tem','ser','sao','foi','isto','esse','essa','the','is','of','and','this','are','have'}

def _norm(value: str) -> str:
    value=unicodedata.normalize('NFKD',value.casefold())
    return ''.join(c for c in value if not unicodedata.combining(c))

def _terms(value: str) -> set[str]:
    return {w for w in re.findall(r'\b[a-z]{3,}\b',_norm(value)) if w not in _STOP}

def audit_claim(claim: str, excerpts: list[str]) -> dict:
    """Conservative surface-form analysis; no semantic-entailment verdict."""
    sources=' '.join(excerpts)
    numbers=set(_NUM.findall(_norm(claim)))
    src_numbers=set(_NUM.findall(_norm(sources)))
    unsupported=sorted(numbers-src_numbers)
    ct=_terms(claim)
    overlap=len(ct & _terms(sources))/max(1,len(ct))
    flags=[]
    if unsupported:flags.append('numbers_absent_from_sources')
    if ct and overlap < .25:flags.append('weak_lexical_grounding')
    # Mismatched negation is weak warning only, not an entailment judgment.
    if bool(_NEG.search(_norm(claim))) and not bool(_NEG.search(_norm(sources))):
        flags.append('negation_not_present_in_sources')
    return {'status':'requires_review' if flags else 'surface_checks_passed_not_verified',
            'flags':flags,'unsupported_numbers':unsupported,'lexical_coverage':round(overlap,3),
            'semantic_entailment_verified':False}
