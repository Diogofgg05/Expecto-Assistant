"""Deterministic reward prototyping for potential future RL experiments.

This does not optimize model weights. Only rewards verifiable arithmetic exercises;
never derive factual truth from language-model self-evaluation.
"""
from __future__ import annotations
from fractions import Fraction
from .reasoning_verifier import exact_arithmetic, VerificationError


def arithmetic_reward(case: dict, candidate: dict) -> dict:
    if not isinstance(case, dict) or not isinstance(candidate, dict):
        raise ValueError('Casos inválidos')
    if case.get('kind') != 'exact_arithmetic' or not isinstance(case.get('expression'), str):
        raise ValueError('Apenas aritmética verificável')
    try:
        correct=Fraction(exact_arithmetic(case['expression']))
        proposed=Fraction(candidate.get('result',''))
        score=1.0 if correct == proposed else 0.0
        return {'reward':score,'expected':str(correct),'valid':True,
                'note':'Recompensa matemática exata; NÃO é um julgamento global de raciocínio'}
    except (VerificationError,ValueError,ZeroDivisionError,TypeError,OverflowError):
        return {'reward':0.0,'expected':None,'valid':False,
                'note':'A recompensa não pôde ser calculada com segurança'}
