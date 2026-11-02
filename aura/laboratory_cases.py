"""Procedural holdouts with independent oracles, never sent in model prompts."""
from dataclasses import dataclass
import hashlib
import random
import re


@dataclass(frozen=True)
class Case:
    id: str
    domain: str
    prompt: str
    expected: str
    evidence: tuple = ()

    def grade(self, answer):
        # Strict output task: verbosity or an unparseable response is a failure.
        value = answer.strip().strip('`').strip()
        return value == self.expected


def generate_cases(seed: int, per_domain=5):
    if not 4 <= per_domain <= 100:
        raise ValueError('per_domain must be 4–100')
    rng = random.Random(seed)
    cases = []
    for i in range(per_domain):
        a, b, c, d = [rng.randrange(-99, 100) for _ in range(4)]
        cases.append(Case(f'math-{i}', 'math',
            f'Qual é o determinante de [[{a},{b}],[{c},{d}]]? Responde apenas com o inteiro.',
            str(a*d-b*c)))
        start, end, step = rng.randint(-12, 3), rng.randint(5, 22), rng.randint(1, 4)
        offset = rng.randint(-9, 9)
        # Oracle uses an explicit accumulation, independent of model reasoning.
        value = 0
        for n in range(start, end, step):
            value += n + offset
        prompt = (f'Qual é a saída deste Python? Responde apenas com o inteiro.\n'
                  f'```python\ntotal = 0\nfor n in range({start}, {end}, {step}):\n'
                  f'    total += n + ({offset})\nprint(total)\n```')
        cases.append(Case(f'code-{i}', 'programming', prompt, str(value)))
        token = 'OBJ-' + str(rng.randrange(100000, 999999))
        amount = rng.randint(100, 900)
        conflict = i % 2 == 0
        sources = ({'id': 's1', 'text': f'O registo {token} contém {amount} unidades.'},
                   {'id': 's2', 'text': f'O registo {token} contém {amount + 1 if conflict else amount} unidades.'})
        question = (f'Quantas unidades tem {token} segundo os dois registos? '
                    'As fontes têm igual autoridade e data. Se divergem, responde INSUFFICIENT. '
                    'Caso contrário responde apenas com o inteiro. Não escolhas uma fonte arbitrariamente.')
        cases.append(Case(f'research-{i}', 'research', question,
                          'INSUFFICIENT' if conflict else str(amount), sources))
    rng.shuffle(cases)
    return cases


def corpus_digest(cases):
    import json
    from dataclasses import asdict
    return hashlib.sha256(json.dumps([asdict(c) for c in cases], sort_keys=True).encode()).hexdigest()
