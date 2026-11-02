"""SchemaMixin: extracted SQL logic. No schema, query or API changes."""
from __future__ import annotations
from .vault import cipher_operational_errors


class SchemaMixin:
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
