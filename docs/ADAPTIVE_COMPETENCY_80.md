# EXPECTO 8.0 — Adaptive Competency Practice

**Status**: feature branch / PR, not part of released main.

The previous source-extraction pipeline and book evaluations were not a
repeatable, model-independent way to identify weak subject areas. This module
adds a lightweight *practice system* with exact mathematical oracles.

## Workflow

1. Explicit user command `treina competências` selects the least assessed area
   initially, then selects the area with the weakest recent correctness.
2. The local deterministic generator produces a question in mathematics,
   Python program output, or classical mechanics; a private numeric answer
   and explanation are persisted in the local database.
3. The user responds with `responde treino <id>: <inteiro>` (or `x,y`
   for linear systems). The database enforces a single pending exercise.
4. The answer is graded by independent Python rules, never by Ollama.
5. History drives difficulty changes (1–3). The user can request a specific
   area or skip a challenge without accruing an incorrect grade.
6. `estado das competências` shows per-domain attempts, correct results,
   recent success and suggested next topic.

The generator does **not** execute arbitrary user code, retrieve the internet,
read private PDFs, fine-tune weights or claim research-level mastery. The
learning is *measured exercise progress*, NOT model-weight learning.

## Safety and privacy

- No new processes, listeners, scheduled training jobs or dependencies.
- One pending task per database; stale tasks expire after 24 hours.
- The expected answer stays inside the database until the user responds.
- No dangerous action is authorized through generated model text.
- Existing SQLCipher data remain intact; only a new isolated practice table
  and indexes are added lazily upon the first explicit training command.
- Scoring requires strict numeric responses; no `eval`, `exec` or user code
  execution.
- Existing memory, consent flags, PDF research, voice and endpoints unchanged.

## Test commands

```bash
python -m pytest -q tests/test_adaptive_competency_v80.py
python -m scripts.check_architecture --check
python -m pytest -q tests
```

Future work: a fully offline spaced-repetition schedule that surfaces *due*
questions only with user opt-in, a human-curated held-out suite for physics
reasoning, and a secure local PDF question importer with provenance.
