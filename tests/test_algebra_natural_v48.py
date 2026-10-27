import pytest
from aura.algebra_natural import explain
from aura.algebra_verifier import AlgebraError

def test_two_variable_equations():
    r=explain('Resolve 2x+y=5; x-y=1')
    assert r['result']['solution_named']=={'x':'2','y':'1'}

def test_three_variable_system():
    r=explain('x+y+z=6; x-y=0; z=2')
    assert r['result']['solution_named']=={'x':'2','y':'2','z':'2'}

def test_exact_determinant():
    assert explain('Calcula o determinante de [[2,1],[3,4]]')['result']['actual']=='5'

def test_inverse():
    assert explain('Calcula a inversa de [[1,2],[3,4]]')['result']['actual']==[['-2','1'],['3/2','-1/2']]

@pytest.mark.parametrize('q',["resolve x*y=1; x+y=2","resolve x**2=4; y=2","resolve x=2; x=3; x=4; x=5","resolve x=1; import os","inversa [[1,2],[3,4]] extra"])
def test_rejects_unsafe_or_ambiguous(q):
    with pytest.raises(AlgebraError):explain(q)
