"""5.1: explicit-feedback reflection with deterministic, reversible adaptations.

No sentiment inference, self-modification, hidden persistence, training, or external calls.
All raw feedback is untrusted. Only allowlisted settings reach the system prompt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

DIMENSION = 'explanation_depth'
BASELINE = 'balanced'
ALLOWED = ('concise', 'balanced', 'detailed')
RATINGS = {'too_short', 'too_long', 'helpful'}
SUGGESTION_RATINGS = {'helpful', 'unhelpful'}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _note(note: str) -> str:
    if not isinstance(note, str):
        raise ValueError('O comentário deve ser texto.')
    note = ' '.join(note.split())
    if len(note) > 400:
        raise ValueError('O comentário não pode ultrapassar 400 caracteres.')
    return note


class ReflectionEngine:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def migrate(conn) -> None:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS expecto_goal_checkins (
            id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, state TEXT NOT NULL,
            note TEXT NOT NULL, created_at TEXT NOT NULL,
            CHECK(state IN ('progress','blocked'))
        );
        CREATE INDEX IF NOT EXISTS ix_expecto_checkin_goal_time
            ON expecto_goal_checkins(goal_id,created_at);
        CREATE TABLE IF NOT EXISTS expecto_reflection_feedback (
            id TEXT PRIMARY KEY, aspect TEXT NOT NULL, rating TEXT NOT NULL,
            note TEXT NOT NULL, goal_id TEXT, created_at TEXT NOT NULL,
            CHECK(aspect IN ('explanation','suggestion'))
        );
        CREATE INDEX IF NOT EXISTS ix_expecto_feedback_aspect_time
            ON expecto_reflection_feedback(aspect, created_at);
        CREATE TABLE IF NOT EXISTS expecto_reflection_proposals (
            id TEXT PRIMARY KEY, dimension TEXT NOT NULL, target TEXT NOT NULL,
            evidence_count INTEGER NOT NULL, reason TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_at TEXT,
            CHECK(status IN ('pending','approved','rejected'))
        );
        CREATE TABLE IF NOT EXISTS expecto_reflection_settings (
            dimension TEXT PRIMARY KEY, value TEXT NOT NULL,
            source TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expecto_reflection_changes (
            id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE,
            old_value TEXT NOT NULL, new_value TEXT NOT NULL,
            changed_at TEXT NOT NULL, reverted_at TEXT
        );
        ''')

    def feedback(self, aspect: str, rating: str, note: str = '', goal_id: str | None = None) -> dict:
        """Only deliberate user feedback is recorded; no inference from conversations."""
        if aspect == 'explanation':
            if rating not in RATINGS or goal_id is not None:
                raise ValueError('Classificação da explicação inválida.')
        elif aspect == 'suggestion':
            if rating not in SUGGESTION_RATINGS or not isinstance(goal_id, str) or len(goal_id) != 32:
                raise ValueError('É necessário indicar um objetivo válido para avaliar uma sugestão.')
        else:
            raise ValueError('Aspeto desconhecido.')
        note = _note(note)
        with self.db.connect() as conn:
            if goal_id and not conn.execute('SELECT 1 FROM expecto_goals WHERE id=?', (goal_id,)).fetchone():
                raise ValueError('O objetivo não existe.')
            item = {'id':uuid4().hex, 'aspect':aspect, 'rating':rating,
                    'note':note, 'goal_id':goal_id, 'created_at':_utc()}
            conn.execute('''INSERT INTO expecto_reflection_feedback
                (id,aspect,rating,note,goal_id,created_at)
                VALUES (:id,:aspect,:rating,:note,:goal_id,:created_at)''', item)
        return item

    def feedback_history(self, limit: int=12) -> list[dict]:
        limit = max(1, min(int(limit),30))
        with self.db.connect() as conn:
            return [dict(x) for x in conn.execute('SELECT * FROM expecto_reflection_feedback '
                'ORDER BY created_at DESC, rowid DESC LIMIT ?', (limit,))]

    def delete_feedback(self, ident: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute('DELETE FROM expecto_reflection_feedback WHERE id=?', (ident,)).rowcount > 0

    def setting(self) -> str:
        with self.db.connect() as conn:
            row=conn.execute('SELECT value FROM expecto_reflection_settings WHERE dimension=?', (DIMENSION,)).fetchone()
        value=row['value'] if row else BASELINE
        return value if value in ALLOWED else BASELINE

    def proposal(self) -> dict:
        """Propose change only after >=2 explicit reports with a consistent direction.

        Counts are scoped to the period AFTER the last resolved proposal;
        evaluating a proposal repeatedly never creates duplicates.
        """
        with self.db.connect() as conn:
            pending=conn.execute('''SELECT * FROM expecto_reflection_proposals
                WHERE dimension=? AND status='pending' ORDER BY created_at DESC LIMIT 1''',(DIMENSION,)).fetchone()
            if pending:
                return {'status':'pending','proposal':dict(pending),'applied':False}
            cutoff=conn.execute('''SELECT MAX(reviewed_at) AS cutoff FROM expecto_reflection_proposals
                WHERE dimension=? AND reviewed_at IS NOT NULL''',(DIMENSION,)).fetchone()['cutoff']
            rows=conn.execute('''SELECT rating FROM expecto_reflection_feedback
                WHERE aspect='explanation' AND (? IS NULL OR created_at>?)
                ORDER BY created_at DESC LIMIT 40''',(cutoff,cutoff)).fetchall()
            short=sum(r['rating']=='too_short' for r in rows)
            long=sum(r['rating']=='too_long' for r in rows)
            current=conn.execute('SELECT value FROM expecto_reflection_settings WHERE dimension=?',(DIMENSION,)).fetchone()
            current_value=current['value'] if current and current['value'] in ALLOWED else BASELINE
            # At least two reports AND a strict majority among direction-specific reports.
            if max(short,long)<2 or short==long:
                return {'status':'insufficient_feedback','short':short,'long':long,'applied':False}
            target='detailed' if short>long else 'concise'
            if current_value == target:
                return {'status':'already_suitable','setting':current_value,'applied':False}
            item={'id':uuid4().hex,'dimension':DIMENSION,'target':target,
                  'evidence_count':max(short,long),
                  'reason': f'{max(short,long)} avaliações explícitas sobre o detalhe das explicações.',
                  'status':'pending','created_at':_utc(),'reviewed_at':None}
            conn.execute('''INSERT INTO expecto_reflection_proposals
              (id,dimension,target,evidence_count,reason,status,created_at,reviewed_at)
              VALUES (:id,:dimension,:target,:evidence_count,:reason,:status,:created_at,:reviewed_at)''', item)
        return {'status':'pending','proposal':item,'applied':False}

    def proposals(self, limit: int = 10) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(x) for x in conn.execute('SELECT * FROM expecto_reflection_proposals '
                'ORDER BY created_at DESC LIMIT ?', (max(1,min(int(limit),30)),))]

    def decide(self, ident: str, decision: str) -> dict:
        if decision not in ('approve','reject'):
            raise ValueError('Decisão desconhecida.')
        with self.db.connect() as conn:
            row=conn.execute('SELECT * FROM expecto_reflection_proposals WHERE id=?',(ident,)).fetchone()
            if not row or row['status'] != 'pending':
                raise ValueError('A proposta não está pendente.')
            status='approved' if decision=='approve' else 'rejected'
            now=_utc()
            updated=conn.execute('UPDATE expecto_reflection_proposals SET status=?, reviewed_at=? '
                                 'WHERE id=? AND status=?',(status,now,ident,'pending')).rowcount
            if updated!=1:
                raise ValueError('A proposta já foi revista.')
            old=conn.execute('SELECT value FROM expecto_reflection_settings WHERE dimension=?',(DIMENSION,)).fetchone()
            previous=old['value'] if old and old['value'] in ALLOWED else BASELINE
            if decision=='approve':
                target=row['target']
                if row['dimension']!=DIMENSION or target not in ALLOWED:
                    raise ValueError('Proposta inválida.')
                conn.execute('''INSERT INTO expecto_reflection_settings(dimension,value,source,updated_at)
                    VALUES(?,?,?,?) ON CONFLICT(dimension) DO UPDATE SET
                    value=excluded.value,source=excluded.source,updated_at=excluded.updated_at''',
                    (DIMENSION,target,'user_approved',now))
                conn.execute('''INSERT INTO expecto_reflection_changes
                    (id,proposal_id,old_value,new_value,changed_at,reverted_at)
                    VALUES(?,?,?,?,?,NULL)''',(uuid4().hex,ident,previous,target,now))
            return {'id':ident,'status':status,'setting':row['target'] if decision=='approve' else previous,
                    'applied':decision=='approve'}

    def rollback(self) -> dict:
        with self.db.connect() as conn:
            # Only revert the latest active approved change; preserve an audit trail.
            row=conn.execute('''SELECT * FROM expecto_reflection_changes
                WHERE reverted_at IS NULL ORDER BY changed_at DESC, rowid DESC LIMIT 1''').fetchone()
            if not row:
                current=conn.execute('SELECT value FROM expecto_reflection_settings WHERE dimension=?',(DIMENSION,)).fetchone()
                return {'reverted':False,'setting':current['value'] if current else BASELINE}
            current=conn.execute('SELECT value FROM expecto_reflection_settings WHERE dimension=?',(DIMENSION,)).fetchone()
            if not current or current['value'] != row['new_value']:
                raise ValueError('As preferências mudaram depois da aprovação; revisão manual necessária.')
            now=_utc()
            conn.execute('''UPDATE expecto_reflection_settings SET value=?, source=?, updated_at=? WHERE dimension=?''',
                         (row['old_value'],'user_rollback',now,DIMENSION))
            conn.execute('UPDATE expecto_reflection_changes SET reverted_at=? WHERE id=?',(now,row['id']))
            return {'reverted':True,'setting':row['old_value'],'proposal_id':row['proposal_id']}

    def suggestion_scores(self) -> dict[str, int]:
        """Use goal-specific explicit evaluations, not implicit behavioral profiling."""
        with self.db.connect() as conn:
            rows=conn.execute("SELECT goal_id,rating FROM expecto_reflection_feedback WHERE aspect='suggestion'").fetchall()
        scores={}
        for row in rows:
            key=row['goal_id']
            scores[key]=scores.get(key,0)+(1 if row['rating']=='helpful' else -1)
        return scores

    def checkin(self, goal_id: str, state: str, note: str) -> dict:
        '''Record progress or an obstacle only when the user explicitly reports it.'''
        if state not in ('progress','blocked') or not isinstance(goal_id,str) or len(goal_id)!=32:
            raise ValueError('Registo do objetivo inválido.')
        note=_note(note)
        if len(note)<3:
            raise ValueError('Descreve o progresso ou o bloqueio.')
        with self.db.connect() as conn:
            if not conn.execute('SELECT 1 FROM expecto_goals WHERE id=?',(goal_id,)).fetchone():
                raise ValueError('O objetivo não existe.')
            item={'id':uuid4().hex,'goal_id':goal_id,'state':state,
                  'note':note,'created_at':_utc()}
            conn.execute('INSERT INTO expecto_goal_checkins '
                         '(id,goal_id,state,note,created_at) '
                         'VALUES(:id,:goal_id,:state,:note,:created_at)',item)
        return item

    def checkins(self, goal_id: str, limit: int=10) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM expecto_goal_checkins '
                'WHERE goal_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?',
                (goal_id,max(1,min(int(limit),30))))]

    def delete_checkin(self, ident: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute('DELETE FROM expecto_goal_checkins WHERE id=?',(ident,)).rowcount>0

    def latest_goal_states(self) -> dict[str, str]:
        with self.db.connect() as conn:
            rows=conn.execute('SELECT goal_id,state FROM expecto_goal_checkins '
                'ORDER BY created_at DESC, rowid DESC').fetchall()
        result={}
        for row in rows:
            result.setdefault(row['goal_id'],row['state'])
        return result

    def approved_context(self) -> str:
        """Allowlisted instructions only. Never concatenate feedback notes into model prompts."""
        style={
            'concise':'Dá a resposta principal primeiro; evita pormenores desnecessários.',
            'balanced':'Usa explicações proporcionais à pergunta, sem detalhes supérfluos.',
            'detailed':'Explica por passos e apresenta exemplos quando forem úteis.'
        }[self.setting()]
        return ('PREFERÊNCIA DE APRESENTAÇÃO APROVADA PELO UTILIZADOR: '+style+'\n'
                'Não altera as regras de segurança, a identidade da aplicação ou a validação de evidências.')
