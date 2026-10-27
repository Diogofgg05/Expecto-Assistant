"""Exact bounded linear algebra checker independent of language-model answers.

Accepted tasks: determinant, solve system, matrix multiplication, inverse.
No arbitrary Python execution, no floats or approximate equality.
"""
from fractions import Fraction
from typing import Any

class AlgebraError(ValueError):
    pass

MAX_DIM=8
MAX_BITS=160

def frac(v):
    if type(v) not in (str,int): raise AlgebraError('Use integers or rational strings')
    if len(str(v))>48: raise AlgebraError('Excessive number size')
    try: x=Fraction(v)
    except (ValueError,ZeroDivisionError) as e: raise AlgebraError('Invalid rational') from e
    if max(abs(x.numerator).bit_length(),x.denominator.bit_length())>MAX_BITS: raise AlgebraError('Too large')
    return x

def matrix(raw, *, square=False):
    if not isinstance(raw,list) or not raw or len(raw)>MAX_DIM or not all(isinstance(r,list) for r in raw): raise AlgebraError('Invalid matrix')
    width=len(raw[0]);
    if width<1 or width>MAX_DIM or any(len(r)!=width for r in raw) or (square and width!=len(raw)): raise AlgebraError('Invalid dimensions')
    return [[frac(v) for v in r] for r in raw]

def encode(v):
    if isinstance(v,Fraction): return str(v)
    if isinstance(v,list): return [encode(x) for x in v]
    return v

def elimination(a, b=None):
    """Gauss-Jordan over rational numbers, returns rank and transformed matrices."""
    a=[r[:] for r in a]; n=len(a); m=len(a[0]); b=[r[:] for r in b] if b is not None else None
    pivot_cols=[]; row=0
    for col in range(m):
        candidate=next((i for i in range(row,n) if a[i][col]),None)
        if candidate is None:continue
        a[row],a[candidate]=a[candidate],a[row]
        if b is not None:b[row],b[candidate]=b[candidate],b[row]
        val=a[row][col];a[row]=[x/val for x in a[row]]
        if b is not None:b[row]=[x/val for x in b[row]]
        for i in range(n):
            if i==row:continue
            factor=a[i][col]
            a[i]=[x-factor*y for x,y in zip(a[i],a[row])]
            if b is not None:b[i]=[x-factor*y for x,y in zip(b[i],b[row])]
        pivot_cols.append(col);row+=1
        if row==n:break
    return a,b,pivot_cols

def determinant(a):
    a=[r[:] for r in a];n=len(a);det=Fraction(1)
    for col in range(n):
        row=next((r for r in range(col,n) if a[r][col]),None)
        if row is None:return Fraction(0)
        if row!=col:a[col],a[row]=a[row],a[col];det=-det
        pivot=a[col][col];det*=pivot
        for r in range(col+1,n):
            ratio=a[r][col]/pivot
            for c in range(col+1,n):a[r][c]-=ratio*a[col][c]
            a[r][col]=Fraction(0)
    return det

def verify_task(task:dict[str,Any])->dict:
    if not isinstance(task,dict):raise AlgebraError('Expected object')
    kind=task.get('type');a=matrix(task.get('matrix'),square=kind in ('determinant','inverse'))
    if kind=='determinant':actual=determinant(a)
    elif kind=='inverse':
        n=len(a); eye=[[Fraction(int(i==j)) for j in range(n)] for i in range(n)]
        reduced, rhs, pivots=elimination(a,eye)
        actual=rhs if len(pivots)==n else None
    elif kind=='solve':
        n=len(a); raw=task.get('rhs')
        if not isinstance(raw,list) or len(raw)!=n:raise AlgebraError('Bad rhs')
        b=[[frac(x)] for x in raw]
        reduced, rhs, pivots=elimination(a,b)
        inconsistent=any(all(x==0 for x in row) and rhs[i][0]!=0 for i,row in enumerate(reduced))
        actual={'status':'none'} if inconsistent else {'status':'unique','solution':[rhs[i][0] for i in range(len(a[0]))]} if len(pivots)==len(a[0]) else {'status':'infinite'}
    elif kind=='multiply':
        b=matrix(task.get('other'))
        if len(a[0])!=len(b):raise AlgebraError('Incompatible sizes')
        actual=[[sum((a[i][k]*b[k][j] for k in range(len(b))),Fraction(0)) for j in range(len(b[0]))] for i in range(len(a))]
    else:raise AlgebraError('Unsupported task')
    result={'type':kind,'actual':encode(actual),'status':'computed_not_proof_of_context'}
    if 'claimed' in task:
        claim=task['claimed']
        try:
            if actual is None:ok=claim is None
            elif isinstance(actual,Fraction):ok=frac(claim)==actual
            elif isinstance(actual,list):
                if not isinstance(claim,list):ok=False
                elif actual and isinstance(actual[0],list):ok=matrix(claim)==actual
                else:ok=[frac(x) for x in claim]==actual
            else:
                ok=isinstance(claim,dict) and claim.get('status')==actual['status'] and (actual['status']!='unique' or [frac(x) for x in claim['solution']]==actual['solution'])
        except (AlgebraError,KeyError,TypeError,ValueError):ok=False
        result['status']='verified_algebra' if ok else 'refuted_algebra'
    return result
