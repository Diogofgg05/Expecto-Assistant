# EXPECTO 7.5 — Core Service Ports + Dependency Injection

## Problem

Previously `AuraEngine` instantiated `MemoryEngine` and `Ollama` directly,
while `EngineServicesMixin` instantiated a dozen more concrete services via
repeated lazy properties. This couples the command router to particular
implementations and makes isolated integration testing harder.

## What changed

- `aura/core/ports.py` contains minimal structural interfaces for chat,
  retrieval/memory and source research. It does not import Ollama, SQLite or
  network frameworks.
- `aura/core/services.py` contains an **explicit whitelist** of service
  factories. The default builders reproduce the existing constructors, import
  adapters only on use, and cache a single instance per `AuraEngine`.
- `AuraEngine(settings, db, *, services=None)` creates a scoped container if
  none is supplied. Existing `AuraEngine(settings, db)` callers still work.
- `engine.llm`, `engine.memory`, `engine.research`, and all other lazy
  service properties preserve their public names and are shared with the
  container. Their original startup order remains memory then Ollama.
- Unit tests inject fake services without starting Ollama or contacting
  external services; default-mode, override, laziness and circular-factory
  validation are covered.

## Dependency direction

```text
API / voice / commands (explicit user authorization)
                  |
                  v
            AuraEngine
                  |
                  v
         CoreServices / ports
          /       |       \\
         v        v        v
   Ollama      SQLite     Researcher
   adapter     memory     adapter
```

The model's output **cannot** choose factories, invoke a privileged action,
change the whitelist or enable network retrieval. Only trusted Python code can
inject services. This is an architecture seam, not a downloadable plugin
system or permission escalation.

## Invariants

- SQLite/SQLCipher schemas, database content and encrypted backups unchanged.
- No changes to prompts, model settings, endpoints, frontend or command routing.
- No new runtime dependencies, background tasks or model downloads.
- `app.py` still owns shutdown of `engine.llm` and `engine.memory`.
- Expensive optional services remain lazy, with one instance per engine.
- Structurally typed ports document capabilities; they do not **yet** prove
  full interchangeability with an arbitrary LLM or RAG provider.
- This refactor is a maintainability change, not evidence of better model
  accuracy, latency or memory use.

## Validation

```bash
python -m pytest -q tests/test_core_services_v75.py
python -m pytest -q tests/test_engine.py tests/test_api.py tests/test_light_core_v702.py
python -m pytest -q tests
```

No merge until the GitHub quality gate and native SQLCipher workflows pass.
The separate open PRs #29-#31 should be reviewed in a deliberate sequence;
this PR does not merge them or modify the protected branch settings.
