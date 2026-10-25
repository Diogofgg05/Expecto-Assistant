"""SQLite persistence with per-operation connections (WAL). No telemetry/cloud DB."""
from __future__ import annotations
import sqlite3
from .vault import VaultLockedError, encrypted_connection, is_plaintext_sqlite, cipher_operational_errors
import re
import json
import calendar
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def months_before(months: int, date: datetime | None = None) -> str:
    """Rolling calendar-month window, not an imprecise 30*months days."""
    date = (date or datetime.now(timezone.utc)).astimezone(timezone.utc)
    month_index = date.year * 12 + (date.month - 1) - months
    year, index = divmod(month_index, 12)
    day = min(date.day, calendar.monthrange(year, index + 1)[1])
    return date.replace(year=year, month=index+1, day=day).isoformat(timespec='seconds')


class Database:
    def __init__(self, path: Path, passphrase: str = "", require_encryption: bool = False):
        self.path = Path(path)
        self._passphrase = passphrase
        self.encrypted = bool(passphrase)
        if require_encryption and not self.encrypted:
            raise VaultLockedError("AURA 2.8 exige a chave da base de dados no arranque. Não existe fallback sem cifragem.")
        if not self.encrypted and self.path.exists() and not is_plaintext_sqlite(self.path) and self.path.stat().st_size:
            raise VaultLockedError("A base parece cifrada. Abre-a com a frase-passe SQLCipher.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY, topic TEXT NOT NULL, title TEXT NOT NULL,
                content TEXT NOT NULL, url TEXT NOT NULL,
                source_type TEXT NOT NULL, evidence_level TEXT NOT NULL,
                learned_at TEXT NOT NULL,
                UNIQUE(topic, url)
            );
            CREATE TABLE IF NOT EXISTS research_jobs (
                id TEXT PRIMARY KEY, topic TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                interval_hours INTEGER NOT NULL DEFAULT 24,
                last_run_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_knowledge_topic ON knowledge(topic);
            ''')
            self._migrate_memories(db)
            self._migrate_episodes(db)
            self._migrate_cognitive_memory(db)
            self._migrate_temporal_memory(db)
            from .relations import RelationMemory
            RelationMemory.migrate(db)
            from .consolidation import ConsolidationEngine
            ConsolidationEngine.migrate(db)
            from .learning import LearningEngine
            LearningEngine.migrate(db)
            from .optimizer import OptimizationLab
            OptimizationLab.migrate(db)
            from .epistemics import EpistemicEngine
            EpistemicEngine.migrate(db)
            from .quality import KnowledgeQuality
            KnowledgeQuality.migrate(db)
            from .factcheck import FactChecker
            FactChecker.migrate(db)
            from .books import BookLearningEngine
            BookLearningEngine.migrate(db)

    @contextmanager
    def connect(self):
        db = (encrypted_connection(self.path, self._passphrase) if self.encrypted
              else sqlite3.connect(self.path, timeout=10))
        if self.encrypted:
            from .vault import sqlcipher_backend
            db.row_factory = sqlcipher_backend().Row
        else:
            db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _migrate_memories(db):
        """Idempotent schema migration; keeps existing memory notes intact."""
        present = {row['name'] for row in db.execute('PRAGMA table_info(memories)')}
        additions = {
            'category': "TEXT NOT NULL DEFAULT 'note'",
            'topic': "TEXT NOT NULL DEFAULT ''",
            'source': "TEXT NOT NULL DEFAULT 'explicit_user'",
            'updated_at': "TEXT NOT NULL DEFAULT ''",
            'status': "TEXT NOT NULL DEFAULT 'active'",
            'importance': 'INTEGER NOT NULL DEFAULT 3',
        }
        needs_reindex = not bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_fts'").fetchone())
        for field, definition in additions.items():
            if field not in present:
                needs_reindex = True
                db.execute(f'ALTER TABLE memories ADD COLUMN {field} {definition}')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS memory_revisions(
                revision_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                previous_content TEXT NOT NULL, revised_at TEXT NOT NULL,
                FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS memory_vectors(
                memory_id TEXT NOT NULL, model TEXT NOT NULL, vector_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, model),
                FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_memory_status ON memories(status);
        ''')
        try:
            db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content, topic, content='memories', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2')""")
            db.executescript('''
                CREATE TRIGGER IF NOT EXISTS memory_insert AFTER INSERT ON memories BEGIN
                    INSERT INTO memory_fts(rowid,content,topic)
                        VALUES (new.rowid,new.content,new.topic);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_delete AFTER DELETE ON memories BEGIN
                    INSERT INTO memory_fts(memory_fts,rowid,content,topic)
                        VALUES('delete',old.rowid,old.content,old.topic);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_update AFTER UPDATE ON memories BEGIN
                    INSERT INTO memory_fts(memory_fts,rowid,content,topic)
                        VALUES('delete',old.rowid,old.content,old.topic);
                    INSERT INTO memory_fts(rowid,content,topic)
                        VALUES(new.rowid,new.content,new.topic);
                END;
            ''')
            if needs_reindex:
                db.execute("INSERT INTO memory_fts(memory_fts) VALUES ('rebuild')")
        except cipher_operational_errors():
            # Minimal SQLite distributions without FTS5: lexical LIKE fallback.
            pass

    def add_memory(self, content: str, category: str = 'note',
                   topic: str = '', importance: int = 3) -> dict:
        content = content.strip()[:2000]
        if not content:
            raise ValueError('A memória não pode estar vazia.')
        if category not in {'note','preference','project','fact','experience'}:
            category = 'note'
        item = {
            'id': uuid4().hex[:12], 'content': content, 'created_at': now(),
            'updated_at': now(), 'category': category, 'topic': topic.strip()[:160],
            'source': 'explicit_user', 'status': 'active',
            'importance': max(1, min(5, int(importance))),
        }
        with self.connect() as db:
            existing = db.execute('''SELECT * FROM memories WHERE status='active'
                                      AND lower(content) = lower(?) LIMIT 1''', (content,)).fetchone()
            if existing:
                return dict(existing)  # Do not create exact duplicates.
            db.execute('''INSERT INTO memories(id,content,created_at,updated_at,
                category,topic,source,status,importance) VALUES(:id,:content,:created_at,
                :updated_at,:category,:topic,:source,:status,:importance)''', item)
        return item

    def memories(self, limit=50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM memories WHERE status='active'
                ORDER BY created_at DESC, rowid DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_memory(self, id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id=? AND status='active'", (id,)).fetchone()
        return dict(row) if row else None

    def update_memory(self, id: str, content: str) -> dict | None:
        content = content.strip()[:2000]
        if not content:
            raise ValueError('A memória corrigida não pode estar vazia.')
        with self.connect() as db:
            old = db.execute("SELECT * FROM memories WHERE id=? AND status='active'", (id,)).fetchone()
            if old is None:
                return None
            db.execute('''INSERT INTO memory_revisions(revision_id,memory_id,previous_content,revised_at)
                VALUES(?,?,?,?)''', (uuid4().hex, id, old['content'], now()))
            db.execute('UPDATE memories SET content=?,updated_at=? WHERE id=?', (content, now(), id))
            db.execute('DELETE FROM memory_vectors WHERE memory_id=?', (id,))
            return dict(db.execute('SELECT * FROM memories WHERE id=?', (id,)).fetchone())

    def delete_memory(self, id: str) -> bool:
        with self.connect() as db:
            # CASCADE also removes all earlier revisions and vectors.
            deleted = db.execute('DELETE FROM memories WHERE id=?', (id,)).rowcount
        return bool(deleted)

    @staticmethod
    def _terms(query: str) -> list[str]:
        stop = {'que','para','sobre','com','das','dos','uma','uns','umas','qual',
                'como','quando','onde','aura','quero','sabes','lembras','minha',
                'minhas','meus','tenho','isto','essa','esse','aquilo','podes',
                'porque','gostava','mim','foi','estou','mais','por','favor'}
        seen, words = set(), []
        for word in re.findall(r'[^\W_]+', query.casefold(), flags=re.UNICODE):
            if len(word) >= 3 and word not in stop and word not in seen:
                words.append(word)
                seen.add(word)
        return words[:16]

    def search_memories(self, query: str, limit: int = 8) -> list[dict]:
        """FTS5 ranking + importance; safe bounded fallback without FTS5."""
        words = self._terms(query)
        if not words:
            return []
        limit = max(1, min(int(limit), 30))
        expression = ' OR '.join('"' + w.replace('"', '') + '"' for w in words)
        with self.connect() as db:
            try:
                rows = db.execute('''SELECT m.*, bm25(memory_fts) AS rank
                    FROM memory_fts JOIN memories m ON m.rowid=memory_fts.rowid
                    WHERE memory_fts MATCH ? AND m.status='active'
                    ORDER BY (bm25(memory_fts) - (m.importance - 3) * 0.8) ASC,
                             m.updated_at DESC LIMIT ?''', (expression, limit)).fetchall()
                return [dict(x) for x in rows]
            except cipher_operational_errors():
                parts = ['(lower(content) LIKE ? OR lower(topic) LIKE ?)'] * len(words)
                params = [p for w in words for p in ('%' + w + '%', '%' + w + '%')]
                rows = db.execute('''SELECT * FROM memories WHERE status='active' AND ('''
                    + ' OR '.join(parts) + ''') ORDER BY importance DESC, updated_at DESC
                    LIMIT ?''', (*params, limit)).fetchall()
                return [dict(x) for x in rows]

    def set_vector(self, id: str, model: str, vector: list[float]):
        if not vector or len(vector) > 8192:
            raise ValueError('Dimensão de embedding inválida.')
        with self.connect() as db:
            db.execute('''INSERT INTO memory_vectors(memory_id,model,vector_json,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(memory_id,model) DO UPDATE SET
                vector_json=excluded.vector_json,updated_at=excluded.updated_at''',
                (id, model, json.dumps(vector), now()))

    def vectors(self, model: str, limit: int = 10000) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT m.*, v.vector_json FROM memory_vectors v
                JOIN memories m ON v.memory_id=m.id WHERE v.model=? AND m.status='active'
                LIMIT ?''', (model, limit)).fetchall()
        return [dict(x) for x in rows]

    def pending_embeddings(self, model: str, limit: int = 40) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT m.* FROM memories m
                LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.model=?
                WHERE m.status='active' AND v.memory_id IS NULL
                ORDER BY m.importance DESC,m.created_at DESC LIMIT ?''',
                (model, limit)).fetchall()
        return [dict(x) for x in rows]

    def export_memories(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT id,content,category,topic,source,importance,
                created_at,updated_at FROM memories WHERE status='active'
                ORDER BY created_at''').fetchall()
        return [dict(x) for x in rows]

    def backup(self, folder: Path) -> Path:
        """Consistent SQLite backup including memory and research knowledge."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ('aura_backup_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
        if self.encrypted:
            # Back up SQLCipher to another SQLCipher DB with SAME key; no plaintext snapshot.
            with self.connect() as source:
                with closing(encrypted_connection(target, self._passphrase)) as destination:
                    source.backup(destination)
            from .vault import verify_encrypted_database
            verify_encrypted_database(target, self._passphrase)
        else:
            with sqlite3.connect(self.path) as source, sqlite3.connect(target) as destination:
                source.backup(destination)
        return target

    @staticmethod
    def _migrate_episodes(db):
        """v2.2: independent episodic memory, never silently purged."""
        db.executescript('''
            CREATE TABLE IF NOT EXISTS conversation_episodes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_episodes_date ON conversation_episodes(created_at);
            CREATE INDEX IF NOT EXISTS ix_episodes_session ON conversation_episodes(session_id,created_at);
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        try:
            missing = not bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='episode_fts'").fetchone())
            db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS episode_fts USING fts5(
                content, content='conversation_episodes', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2')""")
            db.executescript('''
                CREATE TRIGGER IF NOT EXISTS episode_insert AFTER INSERT ON conversation_episodes BEGIN
                    INSERT INTO episode_fts(rowid,content) VALUES(new.rowid,new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS episode_delete AFTER DELETE ON conversation_episodes BEGIN
                    INSERT INTO episode_fts(episode_fts,rowid,content)
                        VALUES('delete',old.rowid,old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS episode_update AFTER UPDATE ON conversation_episodes BEGIN
                    INSERT INTO episode_fts(episode_fts,rowid,content)
                        VALUES('delete',old.rowid,old.content);
                    INSERT INTO episode_fts(rowid,content) VALUES(new.rowid,new.content);
                END;
            ''')
            if missing:
                db.execute("INSERT INTO episode_fts(episode_fts) VALUES ('rebuild')")
        except cipher_operational_errors():
            # Fallback for distributions lacking FTS5.
            pass

    @staticmethod
    def _migrate_cognitive_memory(db):
        """v2.3 additive migration: vector index and attributable extracted knowledge."""
        db.executescript('''
            CREATE TABLE IF NOT EXISTS episode_vectors (
                episode_id TEXT NOT NULL, model TEXT NOT NULL,
                vector_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (episode_id, model),
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_episode_vector_model ON episode_vectors(model);
            CREATE TABLE IF NOT EXISTS automatic_evidence (
                memory_id TEXT NOT NULL, episode_id TEXT NOT NULL,
                quote TEXT NOT NULL, extracted_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, episode_id),
                FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE,
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS extraction_processed (
                episode_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE
            );
        ''')

    @staticmethod
    def _migrate_temporal_memory(db):
        """v2.4: append-only history; one current value per normalized slot."""
        db.executescript('''
            CREATE TABLE IF NOT EXISTS temporal_facts (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                value TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                recorded_at TEXT NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('explicit_user','auto_episode')),
                episode_id TEXT,
                source_quote TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(episode_id) REFERENCES conversation_episodes(id) ON DELETE CASCADE,
                CHECK(valid_to IS NULL OR valid_to >= valid_from)
            );
            CREATE INDEX IF NOT EXISTS ix_temporal_subject_dates
                ON temporal_facts(subject,valid_from DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS ix_temporal_current
                ON temporal_facts(subject) WHERE valid_to IS NULL;
        ''')

    def set_temporal_fact(self, subject: str, value: str, *,
                          source: str='explicit_user', episode_id: str | None=None,
                          quote: str='') -> dict | None:
        """Transactional current-state update preserving all earlier observations.

        valid_from records WHEN AURA LEARNED the state; not a guessed external
        event date. An auto-extracted observation requires an existing user turn.
        """
        from .temporal import canonical_subject,clean_value
        key=canonical_subject(subject) or (subject if subject in {
            'browser','sistema_operativo','distribuicao_linux','editor',
            'linguagem_programacao','modelo_ollama','modelo_ia','framework_frontend'} else None)
        cleaned=clean_value(value)
        if not key or not cleaned:
            raise ValueError('Assunto não suportado ou valor não seguro para memória temporal.')
        if source not in ('explicit_user','auto_episode'):
            raise ValueError('Origem de memória inválida.')
        if source=='auto_episode' and not episode_id:
            raise ValueError('Uma memória automática precisa de fonte.')
        with self.connect() as db:
            if source=='auto_episode':
                evidence=db.execute("SELECT content,role,created_at FROM conversation_episodes WHERE id=?",(episode_id,)).fetchone()
                if not evidence or evidence['role']!='user' or quote!=evidence['content']:
                    raise ValueError('Memória sem mensagem original verificável.')
                # Only called synchronously on newly recorded user utterances.
                # No retrospective backfill, to avoid rewriting newer states.
            current=db.execute('SELECT * FROM temporal_facts WHERE subject=? AND valid_to IS NULL',(key,)).fetchone()
            if current and current['value'].casefold()==cleaned.casefold():
                return dict(current)  # No duplicate version for repeated assertion.
            stamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
            if current:
                db.execute('UPDATE temporal_facts SET valid_to=? WHERE id=?',(stamp,current['id']))
            item=dict(id=uuid4().hex[:12],subject=key,value=cleaned,
                      valid_from=stamp,valid_to=None,recorded_at=stamp,
                      source=source,episode_id=episode_id,source_quote=quote[:3000])
            db.execute('''INSERT INTO temporal_facts(id,subject,value,valid_from,valid_to,
                recorded_at,source,episode_id,source_quote)
                VALUES (:id,:subject,:value,:valid_from,:valid_to,:recorded_at,
                        :source,:episode_id,:source_quote)''',item)
            return item

    def observe_temporal_episode(self, episode_id: str) -> dict | None:
        """Capture only declarative, first-person technical configuration updates."""
        from .temporal import extract_statement
        with self.connect() as db:
            e=db.execute('SELECT * FROM conversation_episodes WHERE id=? AND role=?',
                         (episode_id,'user')).fetchone()
        if not e:
            return None
        parsed=extract_statement(e['content'])
        if not parsed:
            return None
        return self.set_temporal_fact(parsed[0],parsed[1],source='auto_episode',
                                      episode_id=episode_id,quote=e['content'])

    def temporal_current(self, subject: str | None=None, limit: int=30) -> list[dict]:
        from .temporal import canonical_subject
        key=canonical_subject(subject) if subject else None
        if subject and key is None:
            return []
        with self.connect() as db:
            if key:
                rows=db.execute('SELECT * FROM temporal_facts WHERE subject=? AND valid_to IS NULL ORDER BY valid_from DESC LIMIT ?',
                                (key,max(1,min(limit,100)))).fetchall()
            else:
                rows=db.execute('SELECT * FROM temporal_facts WHERE valid_to IS NULL ORDER BY valid_from DESC LIMIT ?',
                                (max(1,min(limit,100)),)).fetchall()
        return [dict(x) for x in rows]

    def temporal_history(self, subject: str, months: int=6, limit: int=30) -> list[dict]:
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if key is None:
            return []
        with self.connect() as db:
            rows=db.execute('''SELECT * FROM temporal_facts
                WHERE subject=? AND (valid_from>=? OR valid_to>=? OR valid_to IS NULL)
                ORDER BY valid_from DESC LIMIT ?''',
                (key,months_before(months),months_before(months),max(1,min(limit,100)))).fetchall()
        return [dict(x) for x in rows]

    def temporal_as_of(self, subject: str, at: str) -> dict | None:
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if not key:
            return None
        try:
            point=datetime.fromisoformat(at)
            if point.tzinfo is None:
                point=point.replace(tzinfo=timezone.utc)
            at=point.astimezone(timezone.utc).isoformat(timespec='microseconds')
        except (ValueError,TypeError):
            raise ValueError('Data inválida; usa AAAA-MM-DD.')
        with self.connect() as db:
            row=db.execute('''SELECT * FROM temporal_facts WHERE subject=?
                AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)
                ORDER BY valid_from DESC LIMIT 1''',(key,at,at)).fetchone()
        return dict(row) if row else None

    def erase_temporal_subject(self, subject: str) -> int:
        """Forget every temporal version for a subject, without restoring old state."""
        from .temporal import canonical_subject
        key=canonical_subject(subject)
        if not key:
            return 0
        with self.connect() as db:
            return db.execute('DELETE FROM temporal_facts WHERE subject=?',(key,)).rowcount

    def temporal_count(self) -> int:
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM temporal_facts').fetchone()[0]

    def pending_episode_embeddings(self, model: str, months: int = 6,
                                   limit: int = 15) -> list[dict]:
        """Index user utterances first, then assistant responses for full recall."""
        with self.connect() as db:
            rows = db.execute('''SELECT e.* FROM conversation_episodes e
                LEFT JOIN episode_vectors v ON v.episode_id=e.id AND v.model=?
                WHERE v.episode_id IS NULL AND e.created_at>=?
                ORDER BY CASE WHEN e.role='user' THEN 0 ELSE 1 END,
                         e.created_at DESC, e.rowid DESC LIMIT ?''',
                (model, months_before(months), max(1, min(60,limit)))).fetchall()
        return [dict(row) for row in rows]

    def save_episode_vector(self, episode_id: str, model: str, values: list[float]) -> None:
        import math
        if not values or len(values)>8192 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):
            raise ValueError('Embedding inválido')
        with self.connect() as db:
            db.execute('''INSERT INTO episode_vectors(episode_id,model,vector_json,created_at)
                SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM conversation_episodes WHERE id=?)
                ON CONFLICT(episode_id,model) DO UPDATE SET
                vector_json=excluded.vector_json,created_at=excluded.created_at''',
                (episode_id,model,json.dumps(values),now(),episode_id))

    def episode_vectors_in_window(self, model: str, months: int = 6,
                                  limit: int = 10000) -> list[dict]:
        """Bounded local cosine scan; production-scale installations need ANN index."""
        with self.connect() as db:
            rows = db.execute('''SELECT e.*,v.vector_json FROM episode_vectors v
                JOIN conversation_episodes e ON e.id=v.episode_id
                WHERE v.model=? AND e.created_at>=?
                ORDER BY e.created_at DESC LIMIT ?''',
                (model,months_before(months),max(1,min(limit,10000)))).fetchall()
        return [dict(row) for row in rows]

    def episode_vector_count(self, model: str, months: int = 6) -> int:
        with self.connect() as db:
            return db.execute('''SELECT count(*) FROM episode_vectors v
                JOIN conversation_episodes e ON e.id=v.episode_id
                WHERE v.model=? AND e.created_at>=?''',
                (model, months_before(months))).fetchone()[0]

    def unprocessed_user_episodes(self, months: int = 6, limit: int = 3) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT e.* FROM conversation_episodes e
                LEFT JOIN extraction_processed p ON p.episode_id=e.id
                WHERE p.episode_id IS NULL AND e.role='user' AND e.created_at>=?
                ORDER BY e.created_at ASC,e.rowid ASC LIMIT ?''',
                (months_before(months),max(1,min(limit,30)))).fetchall()
        return [dict(row) for row in rows]

    def extracted_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM memories WHERE source='auto_episode' AND status='active'").fetchone()[0]

    def save_extractions(self, episode_id: str, candidates: list[dict]) -> int:
        """Store only exact quotes from a user episode; keep evidence links.

        Distinct from explicit notes. Removing the source episode purges any auto
        memory that has no other supporting episode.
        """
        from .privacy import safe_to_extract
        count=0
        with self.connect() as db:
            ep = db.execute("SELECT content,role FROM conversation_episodes WHERE id=?",(episode_id,)).fetchone()
            if ep is None or ep['role']!='user':
                return 0
            source_text=ep['content']
            for entry in candidates[:4]:
                if not isinstance(entry,dict):
                    continue
                quote=entry.get('quote','')
                category=entry.get('category','')
                if (not isinstance(quote,str) or not isinstance(category,str)
                    or category not in ('preference','project','experience')):
                    continue
                quote=quote.strip()
                if (len(quote)<15 or len(quote)>320 or quote.casefold() not in source_text.casefold()
                    or not safe_to_extract(quote)):
                    continue
                existing=db.execute("SELECT id,source FROM memories WHERE status='active' AND lower(content)=lower(?) LIMIT 1",(quote,)).fetchone()
                if existing and existing['source']!='auto_episode':
                    continue  # Never co-opt an explicit user-authored memory.
                memory_id = existing['id'] if existing else uuid4().hex[:12]
                if not existing:
                    db.execute('''INSERT INTO memories(id,content,created_at,updated_at,
                        category,topic,source,status,importance)
                        VALUES(?,?,?,?,?,?,?,?,?)''',
                        (memory_id,quote,now(),now(),category,'','auto_episode','active',3))
                    count+=1
                db.execute('''INSERT OR IGNORE INTO automatic_evidence
                    (memory_id,episode_id,quote,extracted_at) VALUES(?,?,?,?)''',
                    (memory_id,episode_id,quote,now()))
            db.execute('''INSERT INTO extraction_processed(episode_id,completed_at,outcome)
                VALUES(?,?,?) ON CONFLICT(episode_id) DO UPDATE SET
                completed_at=excluded.completed_at,outcome=excluded.outcome''',
                (episode_id,now(),'checked'))
        return count

    def _remove_orphan_auto_memories(self, db):
        db.execute('''DELETE FROM memories WHERE source='auto_episode'
            AND id NOT IN (SELECT memory_id FROM automatic_evidence)''')

    def get_option(self, key: str, default: str = '') -> str:
        with self.connect() as db:
            row = db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_option(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO app_settings(key,value) VALUES(?,?) '
                       'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,value))

    def capture_enabled(self, default: bool = True) -> bool:
        return self.get_option('episodic_capture', 'true' if default else 'false') == 'true'

    def record_exchange(self, session_id: str, user: str, assistant: str) -> list[dict]:
        """Store conversational turns atomically and independently of the UI history."""
        session_id = session_id.strip()[:64] or uuid4().hex
        if not re.fullmatch(r'[\w-]+', session_id, flags=re.UNICODE):
            session_id = uuid4().hex
        items = []
        stamp = now()
        for role, content in [('user',user), ('assistant',assistant)]:
            content = content.strip()[:3000]
            if content:
                items.append({'id':uuid4().hex[:12], 'session_id':session_id,
                              'role':role, 'content':content, 'created_at':stamp})
        with self.connect() as db:
            for entry in items:
                db.execute('INSERT INTO conversation_episodes '
                           '(id,session_id,role,content,created_at) '
                           'VALUES(:id,:session_id,:role,:content,:created_at)', entry)
        return items

    def recent_episodes(self, months: int = 6, limit: int = 30) -> list[dict]:
        cutoff = months_before(months)
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes WHERE created_at>=?
                ORDER BY created_at DESC,rowid DESC LIMIT ?''', (cutoff,max(1,min(200,limit)))).fetchall()
        return [dict(r) for r in rows]

    def episodes_months_ago(self, months: int, limit: int = 25) -> list[dict]:
        """Conversations from one specific calendar-month window (1..N ago)."""
        if months < 1:
            return []
        start, end = months_before(months), months_before(months-1)
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes
                WHERE created_at>=? AND created_at<?
                ORDER BY created_at DESC,rowid DESC LIMIT ?''',
                (start,end,max(1,min(100,limit)))).fetchall()
        return [dict(r) for r in rows]

    def search_episodes(self, query: str, months: int = 6, limit: int = 6) -> list[dict]:
        """Relevant conversations from last N calendar months; no age-based deletion."""
        words = self._terms(query)
        if not words:
            return []
        cutoff = months_before(months)
        limit = max(1,min(50,int(limit)))
        expression = ' OR '.join('"' + w.replace('"','') + '"' for w in words)
        with self.connect() as db:
            try:
                rows = db.execute('''SELECT e.*,bm25(episode_fts) AS rank FROM episode_fts
                    JOIN conversation_episodes e ON e.rowid=episode_fts.rowid
                    WHERE episode_fts MATCH ? AND e.created_at>=?
                    ORDER BY bm25(episode_fts) ASC,e.created_at DESC LIMIT ?''',
                    (expression,cutoff,limit)).fetchall()
            except cipher_operational_errors():
                parts = ['lower(content) LIKE ?'] * len(words)
                rows = db.execute('SELECT * FROM conversation_episodes WHERE created_at>=? AND ('+
                    ' OR '.join(parts)+') ORDER BY created_at DESC LIMIT ?',
                    (cutoff, *['%'+w+'%' for w in words], limit)).fetchall()
        return [dict(r) for r in rows]

    def delete_episode(self, episode_id: str) -> bool:
        with self.connect() as db:
            removed = db.execute('DELETE FROM conversation_episodes WHERE id=?',
                                 (episode_id,)).rowcount
            if removed:
                self._remove_orphan_auto_memories(db)
                from .relations import RelationMemory
                RelationMemory._clean_orphans(db)
            return bool(removed)

    def erase_episodes(self) -> int:
        """Hard-delete episodic records from active DB; backups remain unaffected."""
        with self.connect() as db:
            result = db.execute('DELETE FROM conversation_episodes')
            count = result.rowcount
            self._remove_orphan_auto_memories(db)
            from .relations import RelationMemory
            RelationMemory._clean_orphans(db)
        return count

    def episode_count(self, months: int = 6) -> int:
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM conversation_episodes WHERE created_at>=?',
                              (months_before(months),)).fetchone()[0]

    def export_full_memory(self, months: int = 6) -> dict:
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM conversation_episodes WHERE created_at>=?
                ORDER BY created_at ASC,rowid ASC''', (months_before(months),)).fetchall()
            links = db.execute('''SELECT a.memory_id,a.episode_id,a.quote,a.extracted_at
                FROM automatic_evidence a JOIN conversation_episodes e ON e.id=a.episode_id
                WHERE e.created_at>=?''', (months_before(months),)).fetchall()
        from .relations import RelationMemory
        from .consolidation import ConsolidationEngine
        return {'version': '2.6', 'exported_at': now(), 'lookback_months': months,
                'notes': self.export_memories(), 'conversations': [dict(x) for x in rows],
                'automatic_evidence': [dict(x) for x in links],
                'temporal_history': self.export_temporal_history(),
                'relational_graph': RelationMemory(self).export_graph(),
                'consolidation_summaries': ConsolidationEngine(self).summaries()}

    def export_temporal_history(self) -> list[dict]:
        with self.connect() as db:
            rows=db.execute('SELECT * FROM temporal_facts ORDER BY valid_from ASC').fetchall()
        return [dict(r) for r in rows]

    def backup_if_due(self, folder: Path, days: int = 7) -> Path | None:
        """Make consistent backups weekly, without auto-deleting old ones."""
        last = self.get_option('last_backup_at', '')
        try:
            prior = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - prior < timedelta(days=days):
                return None
        except (ValueError, TypeError):
            pass
        dest = self.backup(folder)
        self.set_option('last_backup_at', now())
        return dest

    def combined_memory_panel(self, months: int = 6) -> list[dict]:
        """One existing holographic memory panel; no new pages or navigation."""
        notes = self.memories(30)
        with self.connect() as conn:
            sources = conn.execute('SELECT memory_id,group_concat(episode_id) AS episode_ids FROM automatic_evidence GROUP BY memory_id').fetchall()
        evidence = {r['memory_id']:r['episode_ids'] for r in sources}
        for note in notes:
            if note.get('source')=='auto_episode':
                note['evidence_episode_ids'] = evidence.get(note['id'],'')
        conversations = self.recent_episodes(months, 25)
        from .temporal import DISPLAY
        temporal = [{**t, 'category':'temporal', 'content':(
            DISPLAY.get(t['subject'],t['subject']) + ': ' + t['value']),
            'created_at':t['valid_from'], 'updated_at':t['valid_from'],
            'temporal_state':'current'} for t in self.temporal_current(limit=15)]
        from .relations import RelationMemory, DISPLAY as GRAPH_DISPLAY
        graph = [{**edge, 'category':'relation',
            'content': (GRAPH_DISPLAY.get(edge['source_kind'],edge['source_kind'])+' '+edge['source_name']+' '+
                        GRAPH_DISPLAY.get(edge['relation_type'],edge['relation_type'])+' '+
                        GRAPH_DISPLAY.get(edge['target_kind'],edge['target_kind'])+' '+edge['target_name']),
            'created_at':edge['created_at'], 'updated_at':edge['created_at']}
            for edge in RelationMemory(self).list_links(limit=25,months=months)]
        from .consolidation import ConsolidationEngine
        summaries = [{**item, 'category':'summary',
            'content':item['content'], 'updated_at':item['created_at']}
            for item in ConsolidationEngine(self).summaries(limit=8)]
        result = summaries + graph + temporal + notes + [{**e, 'category':'conversation',
                            'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']}
                           for e in conversations]
        return sorted(result, key=lambda e:e['created_at'], reverse=True)

    def remember_document(self, topic: str, title: str, content: str, url: str,
                          source_type: str, evidence_level: str) -> dict:
        item = {
            'id': uuid4().hex[:12], 'topic': topic[:160], 'title': title[:240],
            'content': content[:8000], 'url': url[:1500],
            'source_type': source_type, 'evidence_level': evidence_level,
            'learned_at': now(),
        }
        with self.connect() as db:
            db.execute('''INSERT INTO knowledge(id, topic, title, content, url, source_type,
                evidence_level, learned_at) VALUES (:id, :topic, :title, :content, :url,
                :source_type, :evidence_level, :learned_at)
                ON CONFLICT(topic, url) DO UPDATE SET
                title=excluded.title, content=excluded.content,
                evidence_level=excluded.evidence_level, learned_at=excluded.learned_at''', item)
        return item

    def documents(self, query: str = '', limit: int = 30) -> list[dict]:
        with self.connect() as db:
            if query.strip():
                pattern = '%' + query.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
                rows = db.execute('''SELECT * FROM knowledge
                    WHERE topic LIKE ? ESCAPE '!' OR title LIKE ? ESCAPE '!' OR content LIKE ? ESCAPE '!'
                    ORDER BY learned_at DESC LIMIT ?''', (pattern, pattern, pattern, limit)).fetchall()
            else:
                rows = db.execute('SELECT * FROM knowledge ORDER BY learned_at DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create_job(self, topic: str, interval_hours: int = 24) -> dict:
        item = {'id': uuid4().hex[:12], 'topic': topic[:160],
                'interval_hours': max(6, min(interval_hours, 168)), 'created_at': now()}
        with self.connect() as db:
            db.execute('''INSERT INTO research_jobs(id, topic, enabled, interval_hours, created_at)
                VALUES (:id, :topic, 1, :interval_hours, :created_at)
                ON CONFLICT(topic) DO UPDATE SET enabled=1, interval_hours=excluded.interval_hours''', item)
        return item

    def jobs(self, enabled_only: bool = False) -> list[dict]:
        with self.connect() as db:
            if enabled_only:
                rows = db.execute('SELECT * FROM research_jobs WHERE enabled=1 ORDER BY created_at').fetchall()
            else:
                rows = db.execute('SELECT * FROM research_jobs ORDER BY created_at').fetchall()
        return [dict(r) for r in rows]

    def disable_job(self, topic: str) -> bool:
        with self.connect() as db:
            n = db.execute('UPDATE research_jobs SET enabled=0 WHERE lower(topic)=lower(?) AND enabled=1', (topic,)).rowcount
        return bool(n)

    def job_result(self, topic: str, error: str = '') -> None:
        with self.connect() as db:
            db.execute('UPDATE research_jobs SET last_run_at=?, last_error=? WHERE topic=?', (now(), error[:400], topic))

    def due_jobs(self) -> list[dict]:
        current = datetime.now(timezone.utc)
        due = []
        for job in self.jobs(True):
            try:
                prior = datetime.fromisoformat(job['last_run_at']) if job['last_run_at'] else None
            except ValueError:
                prior = None
            if prior is None or current - prior >= timedelta(hours=job['interval_hours']):
                due.append(job)
        return due[:3]  # Resource bound per scheduled cycle.
