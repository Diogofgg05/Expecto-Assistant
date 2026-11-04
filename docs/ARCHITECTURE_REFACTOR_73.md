# EXPECTO 7.3 — Modular Memory Commands

The former 295-line `aura/command_memory.py` mixed privacy, consolidation,
relationship graphs, temporal facts, conversation history, and note CRUD.
This refactor separates these domains **without changing runtime behavior**.

## Dependency path

`user → AuraEngine.command → aura.command_memory.handle_memory_command
→ aura.memory_commands.HANDLERS → domain handler → existing DB/services`

## Domain modules

- `policy.py`: memory dashboard, private mode, consolidation, duplicate/conflict review.
- `relations.py`: opt-in relationship graph writes, removal and queries.
- `temporal.py`: versioned subject changes, historical lookup and as-of queries.
- `episodes.py`: capture and extraction flags, indexing, erasure, search.
- `notes.py`: note search/edit/delete, indexing, encrypted backup and export.

All handlers receive `(engine, original, normalized_key, respond)`, and return
the original response dictionary or `None` if unmatched. They execute in exactly
the former order to avoid altering overlapping natural-language patterns.
The former `aura.command_memory.handle_memory_command` remains an import alias.

## Invariants

- No change to HTTP endpoints, SQL schema, stored memories, or response shape.
- No automatic user data deletion or modification of encryption settings.
- No new runtime dependencies, model downloads or background workers.
- The LLM never authorizes privileged actions; dispatch accepts user input only.
- Heavy services remain lazy and under `AuraEngine` lifecycle control.
- No benchmark performance gains are claimed from organizing code.
- Domain handlers still depend on the engine facade. Narrow protocols and
  explicit dependency injection are future work, not implemented here.

## Validation

```bash
python -m pytest -q tests/test_memory_command_architecture_v73.py
python -m pytest -q tests
```

This is an independent PR, deliberately avoiding modules changed by the 7.1/7.2
laboratory PR. Merge only after reviewing CI and its compatibility tests.
