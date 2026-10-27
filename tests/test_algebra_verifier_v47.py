import pytest
from aura.algebra_verifier import verify_task,AlgebraError

def test_det():
    assert verify_task({'type':'determinant','matrix':[[1,2],[3,4]],'claimed':'-2'})['status']=='verified_algebra'
    assert verify_task({'type':'determinant','matrix':[[1,2],[3,4]],'claimed':'2'})['status']=='refuted_algebra'

def test_inverse():
    t=verify_task({'type':'inverse','matrix':[[1,2],[3,4]],'claimed':[[-2,1],['3/2','-1/2']]})
    assert t['status']=='verified_algebra'
    assert verify_task({'type':'inverse','matrix':[[1,2],[2,4]]})['actual'] is None

def test_system():
    assert verify_task({'type':'solve','matrix':[[2,1],[1,-1]],'rhs':[5,1],'claimed':{'status':'unique','solution':[2,1]}})['status']=='verified_algebra'
    assert verify_task({'type':'solve','matrix':[[1,1],[2,2]],'rhs':[1,3]})['actual']['status']=='none'
    assert verify_task({'type':'solve','matrix':[[1,1],[2,2]],'rhs':[1,2]})['actual']['status']=='infinite'

def test_product():
    assert verify_task({'type':'multiply','matrix':[[1,2],[3,4]],'other':[[2],[4]],'claimed':[[10],[22]]})['status']=='verified_algebra'

def test_rejected():
    for data in [ {'type':'determinant','matrix':[[1,2],[3]]}, {'type':'determinant','matrix':[[1,'__import__("os")'] ,[0,1]]}, {'type':'inverse','matrix':[[1.0]]}, {'type':'multiply','matrix':[[1,2]],'other':[[1]]} ]:
        with pytest.raises(AlgebraError):verify_task(data)
