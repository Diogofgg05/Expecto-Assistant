# EXPECTO 7.9 — Unified Architecture + Reasoning & Performance Laboratory

**Status:** Draft integration PR; not released and not yet merged into `main`.

## What is integrated

- All 26 **non-overlapping** paths from laboratory PR #29 were copied as original
  Git blobs (benchmarks, holdout cases, quality gates, reasoner and documentation).
- Its two conflicting public modules, `aura/engine.py` and `aura/llm.py`,
  were **reconciled** with the architecture from PR #35 instead of overwritten.
- `AuraEngine` preserves `CoreServices` dependency injection and deterministic
  authorized command routing, and now supports checked calculations and
  optional independent reviewer-based local reasoning.
- `Ollama` keeps the modular 7.8 context/prompt/inference pipeline and adds
  structured input budgets, queue telemetry, and optional process/model
  resource observations. The original `reply(question, history, on_token=...)`
  call remains valid.
- `llm_pipeline/inference.py` rejects truncated or incomplete streamed answers
  before an unfinished response could be counted or persisted as complete.
- `llm_pipeline/prompt.py` applies the structured input limit to the user
  message, not to the immutable system and identity instructions.
- Source-based memory, books, RAG, SQLite/SQLCipher schema, opt-in research,
  and the Architecture Guardian checks remain from 7.8.

## Validation

```bash
python -m scripts.check_architecture --check
python -m pytest -q tests/test_unified_laboratory_v79.py
python -m pytest -q tests
```

GitHub Actions also checks Windows/Linux encrypted SQLite installations and
browser voice regressions. Every test must pass before changing the PR from
draft to ready-for-review. A green CI run means the integration passes its
specified tests, not that accuracy or performance on an actual local model has
been demonstrated.

## Next step for reproducible local evaluation

From the checked-out PR branch and with a working local Ollama model:

```bash
ollama list
python -m pip install -r requirements-laboratory.txt
python -m scripts.benchmark_ultra71 --model qwen3:8b --output baseline.json
```

Replace `qwen3:8b` with an **actually installed** model; do not download
unrequested weights or run the suite on sensitive user documents. Run the same
quality corpus for ECO/BALANCED/MAX before recommending any profile.
The default run makes many model calls and is not proof of improvement without
real latency, correctness, memory, and baseline comparisons.

## Merge sequencing

This PR is an integration candidate combining PRs #29 and #35. Keep both
source PRs open until this draft is reviewed and resolved. Do not merge the
source PRs afterwards without accounting for duplicated changes and overlaps.
No production data, default privacy setting, model weights or `main` branch
is intentionally modified by this integration process.
