# EXPECTO 7.0.4 — Database responsibilities (behavior-preserving refactor)

## Goal

`from aura.database import Database` remains the one public entry point.
The original `Database` constructor, `connect()`, all 55 methods
(including private migrations) and the helpers `now()` and
`months_before()` retain their signatures. All original method bodies were
compared against the 7.0.3 baseline, with **zero substantive differences**.

The SQLite schema, SQL statements, FTS indexes, triggers, migrations,
transaction/rollback semantics, retention, SQLCipher connection mode and
backup behavior are unchanged. No data deletion or schema migration is added.

## File structure

| Module | Responsibility |
| --- | --- |
| `aura/database.py` | Public Database façade, constructor and SQL connections |
| `aura/db_shared.py` | Calendar-month and timestamp functions |
| `aura/db_schema.py` | Existing idempotent schema migrations |
| `aura/db_notes.py` | Explicit notes, FTS, vectors and backup |
| `aura/db_episodes.py` | Conversation episodes, embeddings, deletion |
| `aura/db_temporal.py` | Temporal facts, effective dates and history |
| `aura/db_extractions.py` | Source-linked memory extraction |
| `aura/db_settings.py` | Privacy/options, aggregate export and panels |
| `aura/db_research.py` | Documents and opt-in research jobs |

The small mixins call `self.connect()`, with no per-module connection
pools or duplicate database lifecycle.

**Line counts:** `database.py` 848 → approximately 103 lines. The
extracted methods still exist in other files, so overall source size is not
claimed to be lower. This is intended to improve maintainability and reduce
regression risk, not to guarantee lower RAM use.

## Validation and safety

Automated coverage includes:
- All existing project Python regressions and browser Node tests.
- Historical method names and representative signatures.
- Legacy SQLite notes populated before FTS/memory columns existed.
- Idempotent migrations with schema metadata comparisons.
- Cross-domain operations (notes, settings, research jobs and documents).
- Plaintext backup readability and preservation.
- Existing SQLCipher encrypted database tests if the backend is installed;
  there is **no** silent plaintext fallback.

Run with:

```bash
python -m pytest -q tests
node --test tests/test_voice_browser_v54.cjs tests/test_voice_prefetch_v56.cjs tests/test_audio_pipeline_v62.cjs
```

The CI environment does not verify the local SQLCipher installation or
performance with hundreds of thousands of real memory records. Before
shipping on a production encrypted database, make a tested encrypted backup,
restore it into a separate directory and compare schemas and row counts.

## Compatibility note

A single `Database` instance is used for all domains. The composed methods
are inherited directly from mixin classes, so users should not import the
mixins as new public APIs. Import `Database` from `aura.database` exactly
as before.
