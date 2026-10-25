"""AURA 3.3 — limited live source rechecks and auditable factual inquiry.

A claim quoted by a source is *not* a proven fact. Only approved Wikimedia
API endpoint is accessed; never visit user-provided arbitrary URLs. External
checks are explicit, read-only to prior knowledge, fail closed and preserve
uncertainty. Live checking and provenance are separated.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit, unquote
from uuid import uuid4

import httpx

from .database import now
from .learning import quote_present, host
from .quality import KnowledgeQuality

WIKI_API = 'https://pt.wikipedia.org/w/api.php'
MAX_DOCUMENT_BYTES = 120_000
MAX_LIVE_DOCS = 3
ID_PATTERN = re.compile(r'^[0-9a-f]{12}$')


def wikipedia_title(url: str) -> str | None:
    """Extract page title WITHOUT making any request to the supplied URL."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'pt.wikipedia.org'
                or parsed.query or parsed.fragment or not parsed.path.startswith('/wiki/')):
            return None
        title = unquote(parsed.path[len('/wiki/'):]).replace('_', ' ').strip()
        if (not title or len(title) > 170 or '/' in title or any(ord(c) < 32 for c in title)):
            return None
        return title
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return None


def _host_family(url: str) -> str:
    """Only a grouping heuristic: never a proof of editorial independence."""
    domain = host(url)
    # No unsupported public suffix claims: return full host, NOT registered domain.
    return domain


@dataclass(frozen=True)
class LiveExcerpt:
    state: str
    content_hash: str = ''
    note: str = ''


async def fetch_wiki_excerpt(client: httpx.AsyncClient, title: str) -> LiveExcerpt:
    """Fetch from a FIXED allowlisted provider endpoint; no redirects."""
    try:
        response = await client.get(WIKI_API, params={
            'action': 'query', 'titles': title, 'prop': 'extracts',
            'exintro': '1', 'explaintext': '1', 'format': 'json', 'formatversion': '2',
        })
        if response.is_redirect:
            return LiveExcerpt('unavailable', note='Redirecionamento recusado.')
        response.raise_for_status()
        if len(response.content) > MAX_DOCUMENT_BYTES:
            return LiveExcerpt('unavailable', note='Resposta acima do limite.')
        value = response.json()
        pages = value.get('query', {}).get('pages', [])
        if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
            return LiveExcerpt('unavailable', note='Resposta inesperada da API.')
        if pages[0].get('missing') is True:
            return LiveExcerpt('unavailable', note='Página não encontrada.')
        text = pages[0].get('extract', '')
        if not isinstance(text, str) or not text.strip():
            return LiveExcerpt('unavailable', note='Não foi obtido texto de introdução.')
        return LiveExcerpt('available', sha256(text.encode('utf-8')).hexdigest(), text)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return LiveExcerpt('unavailable', note='Falha de rede ou resposta inválida.')


class FactChecker:
    def __init__(self, db):
        self.db = db
        self.quality = KnowledgeQuality(db)

    @staticmethod
    def migrate(conn):
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS factcheck_runs(
          id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, created_at TEXT NOT NULL,
          grade TEXT NOT NULL, report_json TEXT NOT NULL,
          FOREIGN KEY(claim_id) REFERENCES learning_claims(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_factcheck_claim ON factcheck_runs(claim_id,created_at);
        ''')

    def _source_rows(self, claim_id):
        with self.db.connect() as conn:
            rows = conn.execute('''SELECT e.id,e.url,e.exact_quote,e.source_host,
                    k.content AS body,k.url AS archived_url
                    FROM learning_evidence e
                    LEFT JOIN knowledge k ON k.id=e.document_id
                    WHERE e.claim_id=? ORDER BY e.recorded_at,e.id LIMIT 50''',
                    (claim_id,)).fetchall()
        return [dict(r) for r in rows]

    def _analyse_sources(self, rows, quality):
        verified = {x['evidence_id']:x['status'] for x in quality['evidence']}
        groups = defaultdict(set)
        details=[]
        for row in rows:
            status=verified.get(row['id'], 'unavailable')
            text=row['exact_quote']
            if status=='snapshot_unchanged':
                # Archived reports only. Even true copy ≠ true assertion.
                groups[_host_family(row['url'])].add(sha256(' '.join(text.split()).casefold().encode()).hexdigest())
            details.append({'evidence_id':row['id'], 'url':row['url'],
                            'archive_integrity':status,
                            'host':_host_family(row['url']),
                            'live_status':'not_checked', 'live_excerpt_sha256':None,
                            'comment':'Citação arquivada; sem confirmação independente.'})
        good_hosts={k for k in groups if k}
        identical= len(good_hosts)>1 and len({v for vals in groups.values() for v in vals})==1
        return details, len(good_hosts), identical

    def offline(self, claim_id: str) -> dict | None:
        if not ID_PATTERN.fullmatch(claim_id):
            raise ValueError('ID inválido.')
        quality=self.quality.inspect(claim_id)
        if quality is None:
            return None
        details, domains, copies = self._analyse_sources(self._source_rows(claim_id), quality)
        return {
            'claim_id':claim_id,'statement':quality['statement'],
            'knowledge_grade':quality['grade'], 'quality_decision':quality['decision'],
            'checked_at':None,'live_attempted':False, 'live_supported_sources':0,
            'unique_hosts_with_intact_snapshots':domains,
            'identical_reporting_possible':copies,
            'independence_established':False,'fact_proven':False,
            'grade':'blocked' if quality['decision']=='withhold' else 'archived_reporting_only',
            'evidence':details, 'limitations':(
                'Nenhuma fonte externa foi consultada nesta análise. Domínios distintos não provam '
                'independência editorial; coincidência de citações não demonstra verdade factual.'),
        }

    async def verify_live(self, claim_id: str) -> dict | None:
        """Explicit opt-in query. Network only at fixed Wikimedia API endpoint."""
        result=self.offline(claim_id)
        if result is None:
            return None
        if result['grade']=='blocked':
            result['grade']='blocked'
            result['limitations']+=' A hipótese foi retida pela auditoria local: não foi consultada externamente.'
            return result
        rows=self._source_rows(claim_id)
        ids={r['id']:r for r in rows}
        lookup={}
        count=0
        for item in result['evidence']:
            row=ids[item['evidence_id']]
            title=wikipedia_title(row['url'])
            if not title:
                item['live_status']='provider_not_supported'
                item['comment']='Não é uma página da Wikipédia portuguesa; não foi aberto o URL.'
            elif count>=MAX_LIVE_DOCS:
                item['live_status']='limit_reached'
                item['comment']='Máximo de três fontes verificadas por pedido.'
            else:
                lookup[item['evidence_id']] = title
                count+=1
        # No user-controlled URL is ever sent to httpx.
        if lookup:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0),
                                         follow_redirects=False,
                                         headers={'User-Agent':'AURA-FactCheck/3.3 (manual source check)',
                                                  'Accept':'application/json'}) as client:
                async def verify(eid, title):
                    data=await fetch_wiki_excerpt(client,title)
                    return eid,data
                fetched=await asyncio.gather(*(verify(eid,title) for eid,title in lookup.items()))
            fetched=dict(fetched)
            for item in result['evidence']:
                if item['evidence_id'] not in fetched:
                    continue
                res=fetched[item['evidence_id']]
                row=ids[item['evidence_id']]
                if res.state!='available':
                    item['live_status']='unavailable'
                    item['comment']=res.note
                else:
                    item['live_excerpt_sha256']=res.content_hash
                    if quote_present(row['exact_quote'],res.note):
                        item['live_status']='quote_found_in_live_intro'
                        item['comment']='O excerto arquivado continua na introdução pública; isto não prova o conteúdo.'
                    else:
                        item['live_status']='quote_not_found_in_intro'
                        item['comment']='O excerto não aparece na introdução atual; pode estar noutra secção ou ter mudado.'
        supporting=sum(x['live_status']=='quote_found_in_live_intro' for x in result['evidence'])
        result['live_attempted']=bool(lookup)
        result['live_supported_sources']=supporting
        result['checked_at']=now() if lookup else None
        result['grade']=('source_quote_observed_live' if supporting else
                         'source_not_confirmed_live' if lookup else 'no_approved_live_provider')
        result['limitations']=(
            'Consulta limitada à introdução atual de artigos da Wikipédia portuguesa; '
            'não compara todos os conteúdos do artigo, não verifica causalidade, não prova '
            'verdade factual ou independência de outros sites. Faltas de excerto não provam falsidade.')
        # Persist minimal auditable results without changing learning_claims, sources or memories.
        if lookup:
            run_id=uuid4().hex[:12]
            result['run_id']=run_id
            with self.db.connect() as conn:
                conn.execute('''INSERT INTO factcheck_runs(id,claim_id,created_at,grade,report_json)
                    VALUES(?,?,?,?,?)''', (run_id,claim_id,result['checked_at'],result['grade'],
                                         json.dumps(result,ensure_ascii=False)))
        return result

    def latest(self, limit: int = 20) -> list[dict]:
        limit=min(50,max(1,int(limit)))
        with self.db.connect() as conn:
            rows=conn.execute('''SELECT id,claim_id,created_at,grade FROM factcheck_runs
               ORDER BY created_at DESC,rowid DESC LIMIT ?''',(limit,)).fetchall()
        return [dict(r) for r in rows]
