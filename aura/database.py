"""Public Database façade; existing method names and SQL schema stay unchanged."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .vault import VaultLockedError, encrypted_connection, is_plaintext_sqlite, cipher_operational_errors
from .db_shared import now, months_before
from .db_schema import SchemaMixin
from .db_notes import NotesMixin
from .db_episodes import EpisodesMixin
from .db_temporal import TemporalMixin
from .db_extractions import ExtractionsMixin
from .db_settings import SettingsMixin
from .db_research import ResearchMixin


class Database(SchemaMixin, NotesMixin, EpisodesMixin, TemporalMixin, ExtractionsMixin, SettingsMixin, ResearchMixin):
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
            from .living_intelligence import ContinuityEngine
            ContinuityEngine.migrate(db)
            from .reflection import ReflectionEngine
            ReflectionEngine.migrate(db)
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
            from .book_reasoning import BookReasoningEngine
            BookReasoningEngine.migrate(db)
            from .book_semantics import BookSemanticIndex
            BookSemanticIndex.migrate(db)
            from .book_mastery import BookMasteryLab
            BookMasteryLab.migrate(db)
            from .book_iteration import BookIterationLab
            BookIterationLab.migrate(db)

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
