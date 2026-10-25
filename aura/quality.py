"""AURA 3.2 — evidence chain of custody and conservative quality gate.

Only checks LOCAL archived evidence. SHA-256 snapshots detect accidental changes,
not malicious tampering with the encrypted DB. No live web access, LLM judges,
unsupported entailment claims, or autonomous source promotion.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import re

from .epistemics import EpistemicEngine, EQUATION
from .learning import canonical


def digest(value: str) -> str:
    return sha256(value.encode('utf-8')).hexdigest()


def _utc(value: str):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


class KnowledgeQuality:
    def __init__(self, db):
        self.db = db
        self.epistemics = EpistemicEngine(db)

    @staticmethod
    def migrate(conn) -> None:
        conn.executescript("""CREATE TABLE IF NOT EXISTS evidence_snapshots(
            evidence_id TEXT PRIMARY KEY,
            document_sha256 TEXT NOT NULL,
            quote_sha256 TEXT NOT NULL,
            url_sha256 TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            FOREIGN KEY(evidence_id) REFERENCES learning_evidence(id) ON DELETE CASCADE
        );""")
        # DO NOT backfill old evidence. We cannot know its ORIGINAL snapshot.

    def inspect(self, claim_id: str, *, max_age_days: int = 120) -> dict | None:
        if not re.fullmatch(r'[a-f0-9]{12}', claim_id):
            raise ValueError('ID inválido.')
        base = self.epistemics.assess(claim_id)
        if base is None:
            return None
        with self.db.connect() as conn:
            statement = conn.execute('SELECT topic FROM learning_claims WHERE id=?',
                                     (claim_id,)).fetchone()
            rows = conn.execute("""SELECT e.id,e.document_id,e.url,e.exact_quote,e.recorded_at,
                      e.source_host,k.content AS document_content,k.url AS document_url,
                      a.document_sha256,a.quote_sha256,a.url_sha256,a.captured_at
                      FROM learning_evidence e
                      LEFT JOIN knowledge k ON k.id=e.document_id
                      LEFT JOIN evidence_snapshots a ON a.evidence_id=e.id
                      WHERE e.claim_id=? ORDER BY e.recorded_at,e.id""", (claim_id,)).fetchall()
            related = conn.execute("""SELECT id,statement FROM learning_claims
                      WHERE topic=? AND id<>? AND state<>'rejected'
                      ORDER BY created_at DESC LIMIT 300""", (statement['topic'],claim_id)).fetchall()
        evidence = []
        valid_count = 0
        identical_quotes = defaultdict(set)
        documents = defaultdict(set)
        now_time = datetime.now(timezone.utc)
        ages = []
        for r in rows:
            recorded = _utc(r['recorded_at'])
            if recorded and recorded <= now_time:
                ages.append((now_time-recorded).days)
            if r['document_content'] is None:
                status = 'missing_document'
            elif r['document_sha256'] is None:
                status = 'legacy_unattested'
            elif (r['document_sha256'] != digest(r['document_content'])
                  or r['quote_sha256'] != digest(r['exact_quote'])
                  or r['url_sha256'] != digest(r['url'])
                  or r['document_url'] != r['url']):
                status = 'changed_since_capture'
            else:
                status = 'snapshot_unchanged'
                valid_count += 1
            # Repeated text on different domains indicates possible copying,
            # never independent corroboration. It is not definitive plagiarism.
            identical_quotes[canonical(r['exact_quote'])].add(r['source_host'])
            if r['document_content'] is not None:
                documents[digest(r['document_content'])].add(r['source_host'])
            evidence.append({'evidence_id':r['id'],'document_id':r['document_id'],
                             'url':r['url'],'status':status,
                             'captured_at':r['captured_at'], 'recorded_at':r['recorded_at']})
        copies = (any(len(hosts)>1 for hosts in identical_quotes.values())
                  or any(len(hosts)>1 for hosts in documents.values()))
        # Compare only literally identical arithmetic LEFT-hand expressions.
        # Do not label narrative disagreement as a formal contradiction.
        conflict_ids=[]
        lhs = EQUATION.fullmatch(base['statement'])
        if lhs:
            left = re.sub(r'\s+','',lhs.group(1))
            declared = lhs.group(2)
            for other in related:
                match=EQUATION.fullmatch(other['statement'])
                if match and re.sub(r'\s+','',match.group(1))==left and match.group(2)!=declared:
                    conflict_ids.append(other['id'])
        changed = any(e['status'] in ('missing_document','changed_since_capture') for e in evidence)
        # Never use refuted claims, rejected claims or compromised evidence in LLM context.
        blocked = (base['grade'] in ('rejected','unsubstantiated','falsified_calculation')
                   or changed or not evidence)
        max_age_days = min(3650,max(1,int(max_age_days)))
        stale = bool(ages) and min(ages) > max_age_days  # all recorded evidence is old
        return {
            'claim_id':claim_id, 'statement':base['statement'],
            'grade':base['grade'], 'review_state':base['review_state'],
            'decision':'withhold' if blocked else 'use_only_as_qualified_hypothesis',
            'snapshot_status': ('not_available' if not evidence else
                'changed' if changed else 'legacy_or_partial' if valid_count!=len(evidence)
                else 'intact_at_capture'),
            'attested_evidence':valid_count,'evidence_count':len(evidence),
            'repeated_text_across_hosts':copies,
            'independence_confirmed':False,
            'possible_math_conflicts':conflict_ids[:30],
            'archive_age_days':min(ages) if ages else None,
            'review_due':stale, 'evidence':evidence,
            'limitations':('Impressões digitais SHA-256 detetam alterações relativamente à captura '
                'local, não provam autenticidade da fonte. O estado não consulta a internet. '
                'Texto repetido entre domínios não demonstra fontes independentes. '
                'Conflitos detetados são apenas igualdades aritméticas com o mesmo lado esquerdo. '
                'Revisão antiga não significa informação falsa.'),
        }

    def overview(self, limit: int = 50) -> dict:
        limit = min(100,max(1,int(limit)))
        with self.db.connect() as conn:
            ids=[r['id'] for r in conn.execute("""SELECT id FROM learning_claims
              ORDER BY updated_at DESC,id LIMIT ?""",(limit,)).fetchall()]
        items=[self.inspect(cid) for cid in ids]
        decisions=Counter(i['decision'] for i in items)
        snapshots=Counter(i['snapshot_status'] for i in items)
        return {'checked':len(items),'decisions':dict(decisions),
                'snapshot_states':dict(snapshots),
                'repeated_text_warnings':sum(i['repeated_text_across_hosts'] for i in items),
                'math_conflict_warnings':sum(bool(i['possible_math_conflicts']) for i in items),
                'review_due':sum(i['review_due'] for i in items),
                'items':items,
                'caution':'Avaliação offline: nenhuma classificação certifica verdade factual na internet.'}
