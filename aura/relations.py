"""Local, provenance-first relational memory.

No LLM is trusted to create graph edges. Automatic edges only arise from a
small set of literal Portuguese patterns in a *user* episode. All observations
are attributed; they do not establish external facts.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4
from .privacy import safe_to_capture, safe_to_extract_temporal

KINDS = {'project', 'technology', 'problem', 'solution', 'decision'}
TYPES = {
    'uses_technology': ('project', 'technology'),
    'has_problem': ('project', 'problem'),
    'has_decision': ('project', 'decision'),
    'resolves_problem': ('solution', 'problem'),
    'solution_for': ('solution', 'project'),
}
DISPLAY = {
    'project': 'projeto', 'technology': 'tecnologia', 'problem': 'problema',
    'solution': 'solução', 'decision': 'decisão',
    'uses_technology': 'usa', 'has_problem': 'tem problema',
    'has_decision': 'tem decisão', 'resolves_problem': 'resolve',
    'solution_for': 'aplica-se ao projeto',
}


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFD', value.casefold())
    return re.sub(r'\s+', ' ', ''.join(x for x in value if unicodedata.category(x) != 'Mn')).strip()


def clean_name(raw: str) -> str | None:
    """Reject uncertain, multiple, excessively detailed or sensitive labels."""
    if not isinstance(raw, str):
        return None
    value = raw.strip().rstrip('.!').strip()
    if not (2 <= len(value) <= 90) or re.search(r'[\n\r?;|<>{}\[\]"`]', value):
        return None
    if re.search(r'(?i)\b(?:talvez|acho que|se|quando|ou|porque|parece que)\b',value):
        return None
    if not safe_to_capture(value) or not safe_to_extract_temporal(value):
        return None
    return value


def parse_user_relationship(text: str) -> list[tuple[str,str,str,str,str]]:
    """Return explicit source-kind/name, relation, destination-kind/name.

    No paraphrasing or inference: every entity is a literal substring.
    """
    if not isinstance(text, str) or len(text) > 260 or '\n' in text or '?' in text:
        return []
    if not safe_to_extract_temporal(text):
        return []
    line = text.strip().rstrip('.!').strip()
    patterns = (
        (r'^(?:no|para o) projeto (?P<project>.+?) (?:uso|utilizo) (?:a tecnologia )?(?P<tech>.+)$',
         lambda m: [('project', m['project'], 'uses_technology', 'technology', m['tech'])]),
        (r'^o projeto (?P<project>.+?) usa (?:a tecnologia )?(?P<tech>.+)$',
         lambda m: [('project', m['project'], 'uses_technology', 'technology', m['tech'])]),
        (r'^no projeto (?P<project>.+?) (?:tenho|encontrei) (?:o )?problema (?:de|com) (?P<problem>.+)$',
         lambda m: [('project', m['project'], 'has_problem', 'problem', m['problem'])]),
        (r'^no projeto (?P<project>.+?) decidi (?:usar|adotar) (?P<decision>.+)$',
         lambda m: [('project', m['project'], 'has_decision', 'decision', m['decision'])]),
        (r'^resolvi (?:o )?problema (?:de|com) (?P<problem>.+?) (?:com|usando) (?P<solution>.+?)(?: no projeto (?P<project>.+))?$',
         lambda m: [('solution', m['solution'], 'resolves_problem', 'problem', m['problem'])]
             + ([('solution', m['solution'], 'solution_for', 'project', m['project'])] if m.get('project') else [])),
    )
    for pattern, build in patterns:
        matched = re.match(pattern, line, flags=re.IGNORECASE)
        if matched:
            edges = build(matched.groupdict())
            if all(clean_name(edge[1]) and clean_name(edge[4]) for edge in edges):
                return edges
    return []


class RelationMemory:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def migrate(db):
        db.executescript('''
            CREATE TABLE IF NOT EXISTS graph_entities (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('project','technology','problem','solution','decision')),
                name TEXT NOT NULL, name_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(kind,name_key)
            );
            CREATE TABLE IF NOT EXISTS graph_links (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL CHECK(relation_type IN
                    ('uses_technology','has_problem','has_decision','resolves_problem','solution_for')),
                origin TEXT NOT NULL CHECK(origin IN ('explicit_user','auto_episode')),
                episode_id TEXT, source_quote TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES graph_entities(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES graph_entities(id) ON DELETE CASCADE,
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE,
                CHECK((origin='auto_episode' AND episode_id IS NOT NULL)
                   OR (origin='explicit_user' AND episode_id IS NULL))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_graph_edge_evidence
                ON graph_links(source_id,target_id,relation_type,origin,ifnull(episode_id,''));
            CREATE INDEX IF NOT EXISTS ix_graph_source ON graph_links(source_id);
            CREATE INDEX IF NOT EXISTS ix_graph_target ON graph_links(target_id);
            CREATE TABLE IF NOT EXISTS graph_processed (
                episode_id TEXT PRIMARY KEY, processed_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE
            );
        ''')

    @staticmethod
    def _ensure_entity(conn, kind: str, name: str) -> str:
        key = normalize(name)
        old = conn.execute('SELECT id FROM graph_entities WHERE kind=? AND name_key=?', (kind,key)).fetchone()
        if old:
            return old['id']
        id = uuid4().hex[:12]
        conn.execute('INSERT INTO graph_entities (id,kind,name,name_key,created_at) VALUES(?,?,?,?,?)',
                     (id,kind,name,key,datetime.now(timezone.utc).isoformat(timespec='seconds')))
        return id

    def add_link(self, from_kind: str, from_name: str, relation: str,
                 to_kind: str, to_name: str, *, origin='explicit_user',
                 episode_id: str | None=None, quote: str='') -> dict:
        if relation not in TYPES or TYPES[relation] != (from_kind,to_kind):
            raise ValueError('Tipo de relação incompatível.')
        left,right=clean_name(from_name),clean_name(to_name)
        if left is None or right is None:
            raise ValueError('Nomes inválidos ou informação sensível.')
        if origin not in ('explicit_user','auto_episode'):
            raise ValueError('Origem inválida.')
        if origin=='explicit_user' and episode_id is not None:
            raise ValueError('Ligações explícitas não recebem episódio.')
        with self.db.connect() as conn:
            if origin=='auto_episode':
                if not episode_id:
                    raise ValueError('Falta a fonte da relação automática.')
                source=conn.execute('SELECT content,role FROM conversation_episodes WHERE id=?',(episode_id,)).fetchone()
                if not source or source['role']!='user' or quote!=source['content']:
                    raise ValueError('Evidência da relação não corresponde à conversa original.')
                if (from_kind,left,relation,to_kind,right) not in parse_user_relationship(quote):
                    raise ValueError('A afirmação não contém essa relação literal.')
            source_id=self._ensure_entity(conn,from_kind,left)
            target_id=self._ensure_entity(conn,to_kind,right)
            existing=conn.execute('''SELECT * FROM graph_links
                WHERE source_id=? AND target_id=? AND relation_type=? AND origin=?
                    AND ifnull(episode_id,'')=ifnull(?,'')''',
                (source_id,target_id,relation,origin,episode_id)).fetchone()
            if existing:
                return {**dict(existing), 'created':False}
            stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
            item={'id':uuid4().hex[:12],'source_id':source_id,'target_id':target_id,
                  'relation_type':relation,'origin':origin,'episode_id':episode_id,
                  'source_quote':quote[:260] if origin=='auto_episode' else '',
                  'created_at':stamp}
            conn.execute('''INSERT INTO graph_links(id,source_id,target_id,relation_type,origin,
                episode_id,source_quote,created_at) VALUES(:id,:source_id,:target_id,
                :relation_type,:origin,:episode_id,:source_quote,:created_at)''',item)
            return {**item,'created':True}

    def observe_episode(self, episode_id: str) -> int:
        """One attempt per episode; deletions cascade via SQLite foreign keys."""
        with self.db.connect() as conn:
            episode=conn.execute('SELECT role,content FROM conversation_episodes WHERE id=?',(episode_id,)).fetchone()
            done=conn.execute('SELECT 1 FROM graph_processed WHERE episode_id=?',(episode_id,)).fetchone()
        if episode is None or episode['role']!='user' or done:
            return 0
        matches=parse_user_relationship(episode['content'])
        added=0
        for fk,fn,rel,tk,tn in matches:
            entry=self.add_link(fk,fn,rel,tk,tn,origin='auto_episode',
                                episode_id=episode_id,quote=episode['content'])
            added+=int(entry['created'])
        with self.db.connect() as conn:
            conn.execute('INSERT OR IGNORE INTO graph_processed(episode_id,processed_at,outcome) VALUES(?,?,?)',
                         (episode_id,datetime.now(timezone.utc).isoformat(timespec='seconds'),
                          'linked' if added else 'no_pattern'))
        return added

    def backfill(self, months: int=6, limit: int=50) -> dict:
        from .database import months_before
        with self.db.connect() as conn:
            rows=conn.execute('''SELECT e.id FROM conversation_episodes e
              LEFT JOIN graph_processed g ON g.episode_id=e.id
              WHERE e.role='user' AND e.created_at>=? AND g.episode_id IS NULL
              ORDER BY e.created_at ASC,e.rowid ASC LIMIT ?''',
              (months_before(months),max(1,min(limit,200)))).fetchall()
        linked=sum(self.observe_episode(row['id']) for row in rows)
        return {'examined':len(rows),'linked':linked}

    def list_links(self, *, kind: str | None=None, name: str | None=None,
                   limit: int=40, months: int | None=None) -> list[dict]:
        """Graph remains persisted; only auto evidence outside window is excluded."""
        from .database import months_before
        args=[]
        where=[]
        if kind:
            if kind not in KINDS: return []
            where.append('(source.kind=? OR target.kind=?)')
            args.extend((kind,kind))
        if name:
            needle=normalize(name)
            where.append('(source.name_key=? OR target.name_key=?)')
            args.extend((needle,needle))
        if months:
            where.append('(g.origin=? OR (e.created_at IS NOT NULL AND e.created_at>=?))')
            args.extend(('explicit_user',months_before(months)))
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        with self.db.connect() as conn:
            items=conn.execute('''SELECT g.*,source.kind AS source_kind,source.name AS source_name,
                target.kind AS target_kind,target.name AS target_name
                FROM graph_links g JOIN graph_entities source ON source.id=g.source_id
                JOIN graph_entities target ON target.id=g.target_id
                LEFT JOIN conversation_episodes e ON e.id=g.episode_id'''+ clause +
                ' ORDER BY g.created_at DESC,g.rowid DESC LIMIT ?',(*args,max(1,min(limit,150)))).fetchall()
        return [dict(row) for row in items]

    def search_related(self, query: str, limit: int=12, months: int=6) -> list[dict]:
        q=normalize(query)
        if not q:
            return []
        # Never use individual common words or substring matches to attach unrelated data.
        items=self.list_links(limit=150, months=months)
        scored=[]
        for row in items:
            labels=[normalize(row['source_name']),normalize(row['target_name'])]
            match=max((len(label) for label in labels if len(label)>=3 and re.search(
                r'(?<!\w)'+re.escape(label)+r'(?!\w)',q)),default=0)
            if match:
                scored.append((match,row))
        scored.sort(key=lambda pair:(pair[0],pair[1]['created_at']),reverse=True)
        return [row for _,row in scored[:max(1,min(limit,20))]]

    def remove_link(self, link_id: str, *, include_auto=False) -> bool:
        with self.db.connect() as conn:
            predicate='' if include_auto else " AND origin='explicit_user'"
            removed=conn.execute('DELETE FROM graph_links WHERE id=?'+predicate,(link_id,)).rowcount
            if removed:
                self._clean_orphans(conn)
            return bool(removed)

    @staticmethod
    def _clean_orphans(conn):
        conn.execute('''DELETE FROM graph_entities WHERE NOT EXISTS(
            SELECT 1 FROM graph_links WHERE source_id=graph_entities.id OR target_id=graph_entities.id)''')

    def cleanup(self):
        with self.db.connect() as conn:
            self._clean_orphans(conn)

    def stats(self) -> dict:
        with self.db.connect() as conn:
            return {'entities':conn.execute('SELECT count(*) FROM graph_entities').fetchone()[0],
                    'links':conn.execute('SELECT count(*) FROM graph_links').fetchone()[0],
                    'automatic_links':conn.execute("SELECT count(*) FROM graph_links WHERE origin='auto_episode'").fetchone()[0]}

    def export_graph(self) -> dict:
        with self.db.connect() as conn:
            entities=[dict(r) for r in conn.execute('SELECT * FROM graph_entities ORDER BY created_at')]
            edges=[dict(r) for r in conn.execute('''SELECT g.*, s.kind source_kind, s.name source_name,
                 t.kind target_kind, t.name target_name FROM graph_links g
                 JOIN graph_entities s ON s.id=g.source_id JOIN graph_entities t ON t.id=g.target_id
                 ORDER BY g.created_at,g.rowid''')]
        return {'entities':entities,'links':edges}
