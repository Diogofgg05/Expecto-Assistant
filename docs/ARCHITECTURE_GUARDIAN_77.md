# EXPECTO 7.7 — Architecture Guardian

## Mission

Make the modular architecture **enforceable** rather than relying on
human memory or aspirational folder names. The tool is 100% standard-library,
offline, read-only, and runs as part of GitHub's existing CI.

```text
                    UI / Voice / REST
                          |
                   User command router
                          |
                 CoreServices + Ports
                     /    |     \
                 Memory  RAG  Ollama
                    \     |    /
                    SQLite / SQLCipher
```

The diagram above is the intended architectural responsibility map. For a
**source-derived**, current module-dependency map, use:

```bash
python -m scripts.check_architecture --format mermaid
python -m scripts.check_architecture --format json
python -m scripts.check_architecture --check
```

## What CI enforces

1. **Ports stay pure**: `aura.core.ports` must not import application adapters.
2. **Inference stays storage-free**: `llm_pipeline.inference` must not import
   any `aura` module or private-memory infrastructure.
3. **Prompts only depend on identity**: `llm_pipeline.prompt` may import
   the `aura.identity` component, but no database, engine or HTTP service.
4. **RAG does not depend on its caller**: `llm_pipeline.context` cannot import
   the Ollama facade, engine, app, route registrations or service container.
5. **Composition root cannot depend on the HTTP entrypoint**:
   `aura.core.services` must not import `aura.app`, `aura.engine`, or route modules.
6. **No cycles inside the governed layer subgraph**:
   `aura.core.*` and `aura.llm_pipeline.*`. Synthetic cycle cases are tested.
7. **No new monolithic governed modules**: files in these packages must remain
   within 260 physical lines. Legacy modules are listed as *observations* in
   a top-10 complexity report, **not** failed or silently rewritten.

The checker examines imports using `ast`, including imports inside methods,
and resolves Python relative imports. It never executes application code or
loads models. Only imports between indexed application modules are counted.

## What this does NOT claim

- The whole legacy repository has no dependency cycles. It guards only the
  *new core architecture*. It does not see dynamic `importlib` imports.
- Physical lines are not a deep complexity measurement; more quality metrics
  will be needed as the codebase grows.
- Modularization does not prove faster inference, lower RAM use or more
  accurate model outputs. Those need real Ollama benchmarks and holdout data.
- This branch does not integrate existing PR #29 (inference and laboratory),
  #30 (memory commands) or #31 (book reasoning). Those require reviewed
  reconciliation and explicit sequencing.

## Incremental merge strategy

The 7.7 PR targets 7.6 (#33), which targets 7.5 (#32). Integrate #32, rebase
and integrate #33, then retarget 7.7. If #29 is merged first, reconcile its
LLM transport and tests before merging overlapping changes.

Use `python -m pytest -q tests`, GitHub's architecture check and the
Windows/Linux SQLCipher workflow as mandatory gates. Do not change
production settings or existing stored user memory in architecture-only PRs.
