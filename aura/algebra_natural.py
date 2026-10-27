"""Bounded PT-PT algebra question interpreter with exact, auditable calculations.

Only a small explicit grammar is accepted. No LLM or arbitrary code execution.
"""
import ast
import json
import re
from fractions import Fraction
from .algebra_verifier import AlgebraError, verify_task, frac, elimination, matrix

_VAR = re.compile(r"(?<![A-Za-z])([xyz])(?![A-Za-z])",re.I)

def _linear(expr):
    expr=expr.replace(' ', '').replace('−','-').replace('×','*')
    expr=re.sub(r'(?<=\d)(?=[xyzXYZ])','*',expr)
    tree=ast.parse(expr,mode='eval')
    def walk(n):
        if isinstance(n,ast.Expression):return walk(n.body)
        if isinstance(n,ast.Constant) and type(n.value)==int:return ({},frac(n.value))
        if isinstance(n,ast.Name) and n.id.lower() in 'xyz' and len(n.id)==1:return ({n.id.lower():Fraction(1)},Fraction(0))
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            a,c=walk(n.operand);k=-1 if isinstance(n.op,ast.USub) else 1
            return ({v:k*x for v,x in a.items()},k*c)
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub)):
            a,c=walk(n.left);b,d=walk(n.right);k=1 if isinstance(n.op,ast.Add) else -1
            return ({v:a.get(v,0)+k*b.get(v,0) for v in a.keys()|b.keys()},c+k*d)
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Mult,ast.Div)):
            a,c=walk(n.left);b,d=walk(n.right)
            if isinstance(n.op,ast.Mult):
                if a and b:raise AlgebraError('Expressão não linear')
                const=d if a else c; non=a if a else b
                return ({v:x*const for v,x in non.items()},c*d)
            if b or not d:raise AlgebraError('Divisão inválida ou não linear')
            return ({v:x/d for v,x in a.items()},c/d)
        raise AlgebraError('Apenas sistemas lineares simples são suportados')
    try:return walk(tree)
    except (SyntaxError,RecursionError,OverflowError) as e:raise AlgebraError('Expressão inválida') from e

def parse_question(question):
    if not isinstance(question,str) or not (3<=len(question)<=1200):raise AlgebraError('Pergunta inválida')
    q=question.strip(); low=q.lower()
    # Matrix input is strict JSON, not executable Python syntax.
    if '[[' in q:
        start=q.index('[['); dec=json.JSONDecoder()
        try:mat,end=dec.raw_decode(q[start:])
        except json.JSONDecodeError as e:raise AlgebraError('Matriz: usar [[a,b],[c,d]]') from e
        tail=q[start+end:].strip(' .?!')
        if tail:raise AlgebraError('Texto adicional após a matriz não suportado')
        kind='determinant' if 'determinante' in low or 'det(' in low else 'inverse' if 'inversa' in low else None
        if not kind:raise AlgebraError('Indica determinante ou inversa')
        return {'type':kind,'matrix':mat},list('xyz')[:len(mat)]
    # Deliberately require exactly two or three equations and = signs.
    q=re.sub(r'^(resolve|resolver|calcula|calcular|o sistema|sistema|as equações|equações)\s*:?', '', q,flags=re.I).strip()
    eqs=[x.strip() for x in re.split(r'[;\n]',q) if x.strip()]
    if not 2<=len(eqs)<=3 or any(x.count('=')!=1 for x in eqs):raise AlgebraError('Escreve 2 ou 3 equações separadas por ponto e vírgula')
    if len(q)>280:raise AlgebraError('Sistema demasiado longo')
    parsed=[];variables=set()
    for eq in eqs:
        l,r=eq.split('=');a,c=_linear(l);b,d=_linear(r)
        co={v:a.get(v,0)-b.get(v,0) for v in a.keys()|b.keys()}
        variables.update(co)
        parsed.append((co,d-c))
    if not variables or len(variables)>3:raise AlgebraError('Suporta apenas x, y e z')
    vars_=sorted(variables)
    task={'type':'solve','matrix':[[str(co.get(v,0)) for v in vars_] for co,_ in parsed],'rhs':[str(rhs) for _,rhs in parsed]}
    return task,vars_

def explain(question):
    task,variables=parse_question(question)
    result=verify_task(task)
    steps=[]
    if task['type']=='solve':
        a=matrix(task['matrix']);b=[[frac(v)] for v in task['rhs']]
        rr,rb,pivots=elimination(a,b)
        steps=['Normalizar cada equação e formar a matriz aumentada [A|b].',
               'Aplicar eliminação de Gauss-Jordan com operações exatas.',
               'Matriz reduzida: '+json.dumps([[str(x) for x in row]+[str(rb[i][0])] for i,row in enumerate(rr)],ensure_ascii=False),
               'Classificar o sistema através dos pivôs e da consistência.']
        if result['actual']['status']=='unique':
            result['solution_named']={name:str(result['actual']['solution'][i]) for i,name in enumerate(variables)}
            steps.append('Substituir os valores nas equações originais para confirmar o resultado.')
    elif task['type']=='determinant':
        steps=['Usar eliminação com operações racionais exatas para calcular o determinante.']
    else:steps=['Aplicar Gauss-Jordan à matriz [A|I]; se A for singular, não tem inversa.']
    return {'interpreted_task':task,'result':result,'steps':steps,'scope':'Verificação algébrica exata; não demonstra compreensão geral de linguagem natural.'}
