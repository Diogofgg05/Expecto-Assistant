"""AURA 3.1 — Epistemic audit and reproducible verification.

No remote web fetch or model judge: 1) source integrity, 2) support in
archived source, 3) optional exact arithmetic proof. These are different
levels of evidence; none proves arbitrary real-world statements true.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from fractions import Fraction
from uuid import uuid4
from .database import now
from .learning import quote_present, host

# These are only arithmetic identities, not broad natural-language facts.
EQUATION = re.compile(r'^\s*([0-9\s.()+*/\-]{1,120})\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*$', re.ASCII)
NUMBER = re.compile(r'\d+(?:\.\d+)?\Z', re.ASCII)
MAX_BITS = 1024


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Número inválido.')
    # Fraction(str(float)) retains the exact decimal the user typed, instead
    # of introducing machine binary float rounding into comparisons.
    v = Fraction(str(value))
    if abs(v.numerator).bit_length() > MAX_BITS or v.denominator.bit_length() > MAX_BITS:
        raise ValueError('Número demasiado grande.')
    return v


def exact_calculation(expression: str) -> Fraction:
    """Evaluate bounded +-*/ expressions via AST, never eval/exec."""
    if not isinstance(expression, str) or len(expression) > 120 or not re.fullmatch(r'[0-9\s.()+*/\-]+', expression):
        raise ValueError('Só são aceites números e + - * / com parênteses.')
    tree = ast.parse(expression, mode='eval')
    count = [0]

    def visit(node, depth=0):
        count[0] += 1
        if depth > 18 or count[0] > 70:
            raise ValueError('Expressão demasiado complexa.')
        if isinstance(node, ast.Expression):
            return visit(node.body, depth+1)
        if isinstance(node, ast.Constant):
            # Lexical parsing of short decimal/integer; no names, no calls.
            raw = ast.get_source_segment(expression, node)
            if not raw or not NUMBER.fullmatch(raw):
                raise ValueError('Número fora do formato permitido.')
            result = Fraction(raw)
            if abs(result.numerator).bit_length() > MAX_BITS or result.denominator.bit_length() > MAX_BITS:
                raise ValueError('Número demasiado grande.')
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            result = visit(node.operand, depth+1)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            lhs, rhs = visit(node.left,depth+1), visit(node.right,depth+1)
            if isinstance(node.op, ast.Add): result = lhs + rhs
            elif isinstance(node.op, ast.Sub): result = lhs - rhs
            elif isinstance(node.op, ast.Mult): result = lhs * rhs
            else:
                if not rhs: raise ValueError('Divisão por zero.')
                result = lhs / rhs
            if abs(result.numerator).bit_length() > MAX_BITS or result.denominator.bit_length() > MAX_BITS:
                raise ValueError('Resultado demasiado grande.')
            return result
        raise ValueError('Operação não permitida.')
    return visit(tree)


def verify_identity(statement: str) -> dict:
    """Reproduce equation in the claim itself, exact rational arithmetic.

    A correct arithmetic equality is externally reproducible. This must NOT
    be used to prove a source's broader assertions or cause-effect claims.
    """
    if not isinstance(statement, str):
        return {'applicable':False, 'passed':False, 'reason':'Tipo inválido.'}
    match = EQUATION.fullmatch(statement)
    if not match or not NUMBER.fullmatch(match.group(2)):
        return {'applicable':False,'passed':False,
                'reason':'Apenas igualdades aritméticas simples podem ser reproduzidas automaticamente.'}
    try:
        actual = exact_calculation(match.group(1))
        expected = Fraction(match.group(2))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return {'applicable':False,'passed':False,'reason':'Expressão inválida ou fora dos limites.'}
    return {'applicable':True,'passed':actual==expected,
            'computed':str(actual), 'declared':str(expected),
            'reason':'Igualdade reproduzida com aritmética racional exata.' if actual==expected else
                     'A igualdade falhou numa verificação aritmética independente.'}


class EpistemicEngine:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def migrate(conn):
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS epistemic_audits (
                id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                evidence_status TEXT NOT NULL,
                arithmetic_status TEXT NOT NULL,
                grade TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(claim_id) REFERENCES learning_claims(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_epistemic_claim_date ON epistemic_audits(claim_id,created_at);
        ''')

    def assess(self, claim_id: str) -> dict | None:
        if not re.fullmatch(r'[a-f0-9]{12}', claim_id):
            raise ValueError('ID inválido.')
        with self.db.connect() as conn:
            claim = conn.execute('SELECT * FROM learning_claims WHERE id=?',(claim_id,)).fetchone()
            if not claim: return None
            evidence = conn.execute('''SELECT e.url,e.exact_quote,e.source_host,e.document_id,
                 e.recorded_at,k.url AS current_url,k.content AS current_content
                 FROM learning_evidence e LEFT JOIN knowledge k ON k.id=e.document_id
                 WHERE e.claim_id=? ORDER BY e.recorded_at,e.id''',(claim_id,)).fetchall()
        findings = []
        valid = []
        for row in evidence:
            issues=[]
            if row['current_content'] is None:
                issues.append('O documento de origem foi eliminado.')
            elif not quote_present(row['exact_quote'],row['current_content']):
                issues.append('O excerto original já não consta da cópia local do documento.')
            if row['current_url'] != row['url']:
                issues.append('O URL do documento já não coincide com a evidência.')
            if host(row['url']) != row['source_host'] or not host(row['url']):
                issues.append('A origem da evidência é inválida ou foi alterada.')
            if issues:
                findings.append({'document_id':row['document_id'],'valid':False,'issues':issues})
            else:
                valid.append(row)
                findings.append({'document_id':row['document_id'],'valid':True,'issues':[]})
        evidence_status = ('no_evidence' if not evidence else
                           'broken' if len(valid)!=len(evidence) else 'intact')
        verification = verify_identity(claim['statement'])
        # A mathematical truth independently reproduced has its own grade,
        # but only if evidence also remains intact and actually quotes it.
        if claim['state']=='rejected':
            grade='rejected'
        elif evidence_status!='intact':
            grade='unsubstantiated'
        elif verification['applicable'] and not verification['passed']:
            grade='falsified_calculation'
        elif verification['applicable'] and verification['passed'] and all(
            claim['statement'].strip().casefold() in row['exact_quote'].casefold() for row in valid
        ):
            grade='reproduced_calculation'
        elif len({r['source_host'] for r in valid}) >= 2:
            grade='multiple_reports_unverified'
        else:
            grade='quoted_unverified'
        return {
            'claim_id':claim_id,'statement':claim['statement'],
            'review_state':claim['state'], 'evidence_status':evidence_status,
            'source_hosts':sorted({r['source_host'] for r in valid}),
            'evidence_count':len(evidence),'intact_evidence_count':len(valid),
            'arithmetic':verification,'grade':grade,'findings':findings,
            'meaning':('Verificar citações prova apenas integridade documental. '
                       'Várias fontes não garantem independência nem verdade. '
                       'Apenas cálculos aritméticos estritos são reproduzidos localmente; '
                       'a aprovação humana não é prova científica.'),
        }

    def audit(self, claim_id: str) -> dict | None:
        result = self.assess(claim_id)
        if not result: return None
        status = ('not_applicable' if not result['arithmetic']['applicable']
                  else 'passed' if result['arithmetic']['passed'] else 'failed')
        with self.db.connect() as conn:
            conn.execute('''INSERT INTO epistemic_audits
                (id,claim_id,evidence_status,arithmetic_status,grade,findings_json,created_at)
                VALUES(?,?,?,?,?,?,?)''',
                (uuid4().hex[:12],claim_id,result['evidence_status'],status,
                 result['grade'],json.dumps(result,ensure_ascii=False),now()))
        return result

    def audit_all(self, limit: int = 100) -> dict:
        limit = min(100,max(1,int(limit)))
        with self.db.connect() as conn:
            ids=[r['id'] for r in conn.execute(
                'SELECT id FROM learning_claims ORDER BY updated_at DESC,id LIMIT ?', (limit,)).fetchall()]
        reports=[self.audit(cid) for cid in ids]
        grades={}
        for item in reports:
            grades[item['grade']]=grades.get(item['grade'],0)+1
        return {'audited':len(reports),'grades':grades,'reports':reports,
                'caution':'Nenhum relatório transforma automaticamente afirmações da internet em verdades.'}

    def latest(self, limit: int = 20) -> list[dict]:
        limit = min(100,max(1,int(limit)))
        with self.db.connect() as conn:
            rows=conn.execute('''SELECT id,claim_id,grade,evidence_status,
                  arithmetic_status,created_at FROM epistemic_audits
                  ORDER BY created_at DESC,rowid DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(r) for r in rows]
