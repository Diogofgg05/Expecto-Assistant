"""Independent, deterministic adversarial exact-math regression corpus.

These 60 cases check only bounded algebraic operations, not general LLM IQ.
Independent ground truth is built from the 2x2 closed-form determinant and
preselected solutions substituted into equations.
"""
import pytest
from aura.reasoning_runtime import exact_math_reply


def _samples():
    cases = []
    for a in range(-4, 5):
        for b in (-3, 0, 2):
            c = a + 2
            d = b - 1
            # 27 cases, including zero, negative and singular matrices.
            expected = a * d - b * c
            cases.append((f"Calcula o determinante de [[{a},{b}],[{c},{d}]]", expected))
    return cases


@pytest.mark.parametrize("question,expected", _samples())
def test_determinant_closed_form(question, expected):
    answer = exact_math_reply(question)
    assert answer is not None
    assert answer.calculation["result"]["actual"] == str(expected)


@pytest.mark.parametrize("x,y", [
    (-8, -3), (-4, 6), (-2, 0), (-1, 2), (0, 0), (0, 7),
    (1, -5), (2, 1), (3, 9), (4, -2), (7, 4), (9, -9)
])
def test_known_solution_substitution(x, y):
    # det([[2,1],[1,-1]]) = -3 != 0, so solution must be unique.
    first = 2*x+y
    second = x-y
    result = exact_math_reply(f"Resolve 2x+y={first}; x-y={second}")
    assert result is not None
    assert result.calculation["result"]["actual"]["status"] == "unique"
    assert result.calculation["result"]["solution_named"] == {
        "x": str(x), "y": str(y)
    }


@pytest.mark.parametrize("n", range(-10, 11))
def test_inconsistent_equations_never_invent_solution(n):
    r = exact_math_reply(f"Resolve x+y={n}; x+y={n+1}")
    assert r is not None
    assert r.calculation["result"]["actual"]["status"] == "none"
