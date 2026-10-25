"""AURA 2.6 — safe, local, evidence-linked, extractive memory consolidation.

No model-generated claims, automatic deletion or forced merging. Every displayed
summary is a selection of verbatim user statements or stored notes. Source
removal/update invalidates its affected summaries immediately with SQLite triggers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata

from .database import months_before, now
from .privacy import safe_to_capture, safe_to_extract_temporal


STOPWORDS = {
    'a','o','as','os','um','uma','de','do','da','dos','das','ao','na','no','num',
    'em','com','e','ou','mas','que','para','por','como','sobre','meu','minha',
    'isto','isso','tambem','muito','mais','esta','este','esse','essa','agora',
    'tenho','quero','preciso','estou','gostava','podes','pode','quando','onde',
    'porque','amanha','ontem','hoje','voce','tu','eu','nos','ja','vou','fazer',
    'usar','usamos','uso','era','foi','sao','ser','tem','ter','numa','apenas',
    'conversa','falamos','aura',  # AURA re-added below as explicit high-priority project
}


def normalized(value: str) -> str:
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                    if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def topic_terms(value: str) -> set[str]:
    return {x for x in normalized(value).split() if len(x) >= 3 and x not in STOPWORDS}


def _memory_key(item: dict) -> str:
    return normalized(item['content'])


def _same_meaning(a: str, b: str) -> bool:
    """Extremely conservative near-exact duplicate detection, not semantic equivalence."""
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    shared = len(ta & tb) / len(ta | tb)
    return shared >= .84 and SequenceMatcher(None, a, b).ratio() >= .90


def _negation_base(s: str) -> tuple[bool, str] | None:
    """Look only for explicit 'não' negation on an otherwise identical sentence."""
    text = normalized(s)
    # e.g. 'quero notificacoes' <> 'nao quero notificacoes'
    prefix = re.match(r'^(?:eu )?(nao )?(quero|uso|prefiro|gosto de|tenho|aceito|permito) (.{5,})$', text)
    if not prefix:
        return None
    return bool(prefix.group(1)), prefix.group(2) + ' ' + prefix.group(3)


class ConsolidationEngine:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def migrate(db) -> None:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS consolidated_summaries(
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                window_months INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS consolidation_sources(
                summary_id TEXT NOT NULL REFERENCES consolidated_summaries(id) ON DELETE CASCADE,
                source_type TEXT NOT NULL CHECK(source_type IN ('memory','episode')),
                source_id TEXT NOT NULL,
                PRIMARY KEY(summary_id,source_type,source_id)
            );
            CREATE INDEX IF NOT EXISTS ix_consolidation_topic ON consolidated_summaries(topic);
            CREATE INDEX IF NOT EXISTS ix_consolidation_source
                ON consolidation_sources(source_type,source_id);
            CREATE TRIGGER IF NOT EXISTS summary_invalidate_memory_delete
                AFTER DELETE ON memories BEGIN
                DELETE FROM consolidated_summaries WHERE id IN
                    (SELECT summary_id FROM consolidation_sources
                     WHERE source_type='memory' AND source_id=OLD.id);
            END;
            CREATE TRIGGER IF NOT EXISTS summary_invalidate_memory_update
                AFTER UPDATE OF content,topic,status ON memories BEGIN
                DELETE FROM consolidated_summaries WHERE id IN
                    (SELECT summary_id FROM consolidation_sources
                     WHERE source_type='memory' AND source_id=OLD.id);
            END;
            CREATE TRIGGER IF NOT EXISTS summary_invalidate_episode_delete
                AFTER DELETE ON conversation_episodes BEGIN
                DELETE FROM consolidated_summaries WHERE id IN
                    (SELECT summary_id FROM consolidation_sources
                     WHERE source_type='episode' AND source_id=OLD.id);
            END;
            CREATE TRIGGER IF NOT EXISTS summary_invalidate_episode_update
                AFTER UPDATE OF content,created_at ON conversation_episodes BEGIN
                DELETE FROM consolidated_summaries WHERE id IN
                    (SELECT summary_id FROM consolidation_sources
                     WHERE source_type='episode' AND source_id=OLD.id);
            END;
        ''')

    def _sources(self, months: int) -> tuple[list[dict],list[dict],list[str]]:
        cutoff = months_before(months)
        with self.db.connect() as conn:
            notes = [dict(r) for r in conn.execute('''
                SELECT id,content,topic,category,source,updated_at AS stamp
                FROM memories WHERE status='active'
                ORDER BY updated_at DESC LIMIT 1000''')]
            episodes = [dict(r) for r in conn.execute('''
                SELECT id,session_id,role,content,created_at AS stamp
                FROM conversation_episodes WHERE role='user' AND created_at>=?
                ORDER BY created_at DESC, rowid DESC LIMIT 2000''',(cutoff,))]
            projects = [r['name'] for r in conn.execute('''
                SELECT name FROM graph_entities WHERE kind='project'
                ORDER BY name LIMIT 60''')]
        # Summaries intentionally ignore assistant outputs to avoid turning model
        # hallucinations into apparently independent factual memories.
        episodes = [e for e in episodes if safe_to_extract_temporal(e['content'])]
        notes = [n for n in notes if safe_to_extract_temporal(n['content'])]
        return notes, episodes, projects

    def consolidate(self, months: int=6, *, max_topics: int=14,
                    max_sources_per_topic: int=12) -> dict:
        """Rebuild bounded, verifiable topic dossiers. Never changes/deletes user memories."""
        months = max(1,min(int(months),60))
        max_topics = max(1,min(int(max_topics),30))
        max_sources_per_topic = max(2,min(int(max_sources_per_topic),25))
        notes, episodes, projects = self._sources(months)
        # Explicit user topics and existing project names take priority.
        candidates: dict[str,str] = {}
        for project in projects:
            token = normalized(project)
            if 3 <= len(token) <= 50:
                candidates[token] = project[:80]
        for note in notes:
            t = note['topic'].strip()
            norm = normalized(t)
            if t and 3 <= len(norm) <= 50:
                candidates[norm] = t[:80]
        # High-frequency recognizable technical topics based on distinct user
        # utterances. Exclude uncommon terms to avoid automatically exposing
        # arbitrary sensitive nouns as topic headers.
        whitelisted = {'aura','novaex','ollama','sqlite','python','linux',
                       'memoria','browser','brave','wine','fedora',
                       'react','github','programacao','matematica','agentes'}
        freq = Counter()
        for message in episodes:
            freq.update(topic_terms(message['content']) & whitelisted)
        for word, count in freq.most_common(20):
            if count >= 2:
                candidates.setdefault(word,word.upper() if word in {'aura','novaex'} else word.title())
        # AURA project gets a topic only if it is actually mentioned, to avoid
        # adding empty or artificial summaries.
        if sum('aura' in normalized(e['content']).split() for e in episodes) >= 2:
            candidates.setdefault('aura','AURA')

        rows = []
        for token, display in list(candidates.items()):
            words = set(token.split())
            chosen=[]
            for note in notes:
                if words.issubset(set(normalized(note['topic']).split())) or words.issubset(set(normalized(note['content']).split())):
                    chosen.append(('memory',note['id'],note['content'].strip(),note['stamp']))
            for ep in episodes:
                if words.issubset(set(normalized(ep['content']).split())):
                    chosen.append(('episode',ep['id'],ep['content'].strip(),ep['stamp']))
            # Two separate sources are required for meaningful consolidation.
            if len(chosen) < 2:
                continue
            chosen.sort(key=lambda x:x[3],reverse=True)
            # Keep all source identifiers in the data model for the selected
            # excerpts and make the claim obviously extractive, not synthesized.
            selected=[]
            seen=set()
            for item in chosen:
                key=normalized(item[2])
                if key in seen:
                    continue
                seen.add(key)
                selected.append(item)
                if len(selected)>=max_sources_per_topic:
                    break
            if len(selected)<2:
                continue
            rendered = [f"Síntese de excertos registados sobre {display} (não verificados independentemente):"]
            for kind, source_id, content, stamp in selected:
                excerpt=' '.join(content.split())[:230]
                rendered.append(f'• «{excerpt}» [{kind}:{source_id}; {stamp[:10]}]')
            text='\n'.join(rendered)[:6000]
            summary_id=hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]
            rows.append((summary_id,display,text,selected))
            if len(rows)>=max_topics:
                break

        with self.db.connect() as conn:
            # Atomic replacement: old dossiers are projections, not user data.
            conn.execute('DELETE FROM consolidated_summaries')
            for sid,topic,body,sources in rows:
                conn.execute('''INSERT INTO consolidated_summaries
                    (id,topic,content,source_count,window_months,created_at)
                    VALUES(?,?,?,?,?,?)''',(sid,topic,body,len(sources),months,now()))
                conn.executemany('''INSERT INTO consolidation_sources
                    (summary_id,source_type,source_id) VALUES(?,?,?)''',
                    [(sid,k,s) for k,s,_content,_date in sources])
            # Set last-run only after successful commit; read during scheduler.
            conn.execute("INSERT INTO app_settings(key,value) VALUES('last_consolidated_at',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now(),))
        return {'summaries':len(rows),'examined_notes':len(notes),
                'examined_user_messages':len(episodes),'window_months':months,
                'automatic_merges':0,'automatic_deletions':0}

    def summaries(self, topic: str='',limit: int=20) -> list[dict]:
        limit=max(1,min(int(limit),50))
        with self.db.connect() as conn:
            rows=conn.execute('SELECT * FROM consolidated_summaries ORDER BY created_at DESC,topic LIMIT 50').fetchall()
            all_sources=conn.execute('SELECT * FROM consolidation_sources').fetchall()
        source_map=defaultdict(list)
        for src in all_sources:
            source_map[src['summary_id']].append({'type':src['source_type'],'id':src['source_id']})
        wanted = topic_terms(topic)
        result=[]
        for row in rows:
            d=dict(row)
            if wanted and not (wanted & topic_terms(d['topic'])) and normalized(topic) not in normalized(d['topic']):
                continue
            d['sources']=source_map[d['id']]
            result.append(d)
            if len(result)>=limit:break
        return result

    def duplicate_candidates(self,limit: int=12) -> list[dict]:
        with self.db.connect() as conn:
            notes=[dict(r) for r in conn.execute('''SELECT id,content,category,topic
                FROM memories WHERE status='active' ORDER BY created_at DESC LIMIT 250''')]
        groups=[]
        used=set()
        for i,one in enumerate(notes):
            if one['id'] in used:continue
            key=_memory_key(one)
            similar=[other for other in notes[i+1:]
                     if other['id'] not in used and other['category']==one['category']
                     and _same_meaning(key,_memory_key(other))]
            if similar:
                group=[one]+similar
                used.update(x['id'] for x in group)
                groups.append({'kind':'possible_duplicate','count':len(group),
                    'memory_ids':[x['id'] for x in group],
                    'examples':[x['content'][:200] for x in group],
                    'note':'Proposta de revisão: não há fusão nem apagamento automático.'})
                if len(groups)>=max(1,min(limit,50)):break
        # Repeated user utterances in the six-month window are also reviewable.
        # Do not merge or remove conversation records.
        remaining=max(0,max(1,min(limit,50))-len(groups))
        if remaining:
            with self.db.connect() as conn:
                turns=[dict(x) for x in conn.execute("""SELECT id,content FROM conversation_episodes
                    WHERE role='user' AND created_at>=? ORDER BY created_at DESC LIMIT 800""",
                    (months_before(6),))]
            buckets=defaultdict(list)
            for episode in turns:
                if safe_to_extract_temporal(episode['content']):
                    k=normalized(episode['content'])
                    if 12<=len(k)<=300:
                        buckets[k].append(episode)
            for same in buckets.values():
                if len(same)<2:
                    continue
                groups.append({'kind':'repeated_conversation','count':len(same),
                    'episode_ids':[x['id'] for x in same[:20]],
                    'examples':[x['content'][:200] for x in same[:2]],
                    'note':'Mensagens repetidas; não foram fundidas nem apagadas.'})
                if len(groups)>=max(1,min(limit,50)):
                    break
        return groups

    def review_candidates(self,limit: int=20) -> list[dict]:
        result=[]
        with self.db.connect() as conn:
            notes=[dict(r) for r in conn.execute('''SELECT id,content FROM memories
                WHERE status='active' ORDER BY created_at DESC LIMIT 300''')]
            subjects=conn.execute('''SELECT subject,count(DISTINCT lower(value)) AS different
                FROM temporal_facts GROUP BY subject HAVING count(DISTINCT lower(value))>1
                LIMIT 50''').fetchall()
            for subj in subjects:
                history=[dict(x) for x in conn.execute('''SELECT id,value,valid_from,valid_to
                    FROM temporal_facts WHERE subject=? ORDER BY valid_from DESC LIMIT 10''',(subj['subject'],))]
                result.append({'kind':'historical_change','subject':subj['subject'],
                    'values':[{'id':x['id'],'value':x['value'],'date':x['valid_from']} for x in history],
                    'note':'Mudança ao longo do tempo; não é necessariamente uma contradição.'})
            buckets=defaultdict(lambda:{True:[],False:[]})
            for item in notes:
                parsed=_negation_base(item['content'])
                if parsed:
                    negative, base=parsed
                    buckets[base][negative].append(item)
            for base, groups in buckets.items():
                if groups[False] and groups[True]:
                    result.append({'kind':'possible_conflict','subject':base,
                        'memory_ids':[groups[False][0]['id'],groups[True][0]['id']],
                        'examples':[groups[False][0]['content'],groups[True][0]['content']],
                        'note':'Afirmações opostas: verificar contexto e datas antes de corrigir.'})
        return result[:max(1,min(limit,50))]

    def stats(self) -> dict:
        with self.db.connect() as conn:
            count=conn.execute('SELECT count(*) FROM consolidated_summaries').fetchone()[0]
            sources=conn.execute('SELECT count(*) FROM consolidation_sources').fetchone()[0]
        return {'summaries':count,'linked_sources':sources,
                'duplicates_for_review':len(self.duplicate_candidates()),
                'possible_conflicts':sum(x['kind']=='possible_conflict' for x in self.review_candidates()),
                'last_consolidated_at':self.db.get_option('last_consolidated_at','')}

    def if_due(self,months: int=6,hours: int=24) -> dict | None:
        stamp=self.db.get_option('last_consolidated_at','')
        try:
            recent=datetime.fromisoformat(stamp)
            if datetime.now(timezone.utc)-recent < timedelta(hours=hours):
                return None
        except (ValueError,TypeError):
            pass
        return self.consolidate(months)
