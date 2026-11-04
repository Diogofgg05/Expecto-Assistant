# EXPECTO 7.8 — Unified Architecture Integration Candidate

**Status:** Integration branch / PR; NOT a released version or part of `main`.

## Why this branch exists

The architecture changes were implemented and tested in separate PRs but
remained fragmented. This branch combines independently reviewed source
snapshots **without automatically merging `main` or changing persisted data**:

| Original PR | Capability | Source |
|---|---|---|
| #30 | Domain-specific memory commands | `aura/memory_commands/*` |
| #31 | Evidence-first book reasoning components | `aura/book_reasoning_components/*` |
| #32 | Scoped, injectable services and core ports | `aura/core/*` |
| #33 | LLM context/prompt/transport pipeline | `aura/llm_pipeline/*` |
| #34 | Architectural dependency guardian in CI | `scripts/check_architecture.py` |

The #32-#34 changes already form the ancestry of this integration branch.
The #30 and #31 file changes are imported as their existing exact Git blobs.
They have disjoint paths from each other and from the prior #34 changes.

**Deliberately excluded:** PR #29 contains changes to the same inference,
engine and context paths as #32/#33. It needs an explicit review of its lab,
stream validation and API changes; overwriting one side would risk losing
functional improvements or safety checks. Do not close or merge #29 blindly.

## New safeguards in the integration PR

- Guarded import directions, cycle detection and line budgets now cover
  `aura.memory_commands` and `aura.book_reasoning_components` as well as
  `aura.core` and `aura.llm_pipeline`.
- Cross-domain offline regression test uses one real local SQLite database,
  normal user memory commands, privacy-mode controls and a stubbed book
  model/retriever. It never starts Ollama or requests external web access.
- The GitHub Quality Gate tests the **combined** code, not independent diffs.
- Windows/Linux SQLCipher installation and persistence checks run on the
  entire integration candidate.

## Review / release procedure

1. Verify the integrated quality gate and both SQLCipher platform jobs pass.
2. Audit the entire integration PR to `main`, including its 5 source PRs.
3. Confirm backups and data migrations on a disposable local test database.
4. Merge the reviewed integration PR only when approved. Older constituent PRs
   should then be reconciled or closed to avoid double-merging.
5. Rebase PR #29 onto the integrated architecture and run laboratory benchmarks
   with **real local Ollama**. No speed / accuracy claim is made before that.

## Commands

```bash
python -m scripts.check_architecture --check
python -m scripts.check_architecture --format mermaid
python -m pytest -q tests/test_architecture_integration_v78.py
python -m pytest -q tests
```

No SQL schema, prompts, weights, application routes, memory retention policies,
voice UI or binary dependencies are intentionally changed by integration.
