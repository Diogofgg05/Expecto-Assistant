# EXPECTO 7.6 — Separation of RAG, prompts and inference

The previously monolithic `aura/llm.py` combined retrieval, evidence
selection, system prompt composition, Ollama transport, model fallback,
streaming and usage telemetry. The public Ollama facade now delegates to:

- `aura/llm_pipeline/context.py` — private memory and knowledge retrieval,
  ranking and existing context limits.
- `aura/llm_pipeline/prompt.py` — identity and safety system prompt and
  bounded conversation history.
- `aura/llm_pipeline/inference.py` — local Ollama HTTP, optional model
  fallback, streaming callbacks and anonymous usage observations.

`Ollama(settings, db, memory=None)`, `reply`, `_reply_impl`, `health`,
`loaded_models`, `_transport`, `aclose`, `SYSTEM`, and the existing
transport test monkeypatch location remain compatible.

No intentional changes to response text, model prompts, failure handling,
personal-memory capture, SQLCipher, API endpoints or UI. Untrusted context
cannot grant commands or tool permissions. No new mandatory dependencies or
model downloads. The separate PR #29 introduces additional stream completion
validation that is NOT silently included in this refactor.

This is **stacked on #32** (EXPECTO 7.5), not yet in main. Review #32 first,
then retarget 7.6 to main and reconcile overlaps with #29 before merging.

Validation:
```bash
python -m pytest -q tests/test_llm_pipeline_v76.py
python -m pytest -q tests/test_performance_engine_v60.py tests/test_context_selection_v66.py
python -m pytest -q tests
```

Modularization is not itself evidence of better latency, memory or accuracy.
