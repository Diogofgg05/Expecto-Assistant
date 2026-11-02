# 7.0.6 follow-up — 2026-11-02

Baseline: main 33f7d8c7378863f3236ce9e59081710e1b4c049e.

## Verified execution

The Linux installer completed in a fresh Python 3.12 virtual environment. sqlcipher3 0.6.4 reports SQLCipher 4.19.0 community. The encrypted migration/backup, Database facade and modular API tests passed: 14 passed, zero skipped. Full Python regression: 318 passed, 1 skipped (20.87s). One Starlette TestClient/httpx deprecation warning. This is Linux evidence only; Windows execution is still pending hosted CI. The existing matrix executes actual installers on both platforms.

The API split already exists on main: five route modules and app.py reduced from the reported 521 lines to 143. This follow-up removes unused imports without changing route registration or public model imports. Linux now checks PRAGMA cipher_version before reporting successful installation.

## Review of all nine open PRs

Read-only git merge-tree checks against the baseline show:

| PR | Merge result | Required action |
|---|---|---|
| #1 | No textual conflict | Experimental verifier is not production integration. Validate independent-model behavior and real benchmarks before promotion. |
| #2 | Conflicts in app, engine, living_intelligence, orb | Port only missing lazy-service/lifecycle behavior; preserve current modular API. |
| #3 | Same conflicts plus llm | Reconcile adaptive compute with current inference implementation before porting. |
| #4 | Same as #3 | Isolate reasoning changes and tests from inherited compute/chiplet changes. |
| #5 | Same as #3 | Isolate provenance and adversarial RAG fixes; do not replace current retrieval wholesale. |
| #6 | Same as #3 plus Windows installer | Retains useful environment-version guards and binary-only SQLCipher install policy; reconcile with current --ci behavior. |
| #7 | Conflicts also in memory, installer, web/app, web/index | Large accumulated branch including processing changes; separate microphone changes from unrelated optimizations. |
| #8 | Conflicts also in installer, web/app, web/index | Isolate media/voice changes and retest cancellation and local-origin boundaries. |
| #10 | Conflicts in app and engine | Current scope exceeds title: includes benchmark tooling and RAG changes. Isolate changes before merge. |

Specific #10 finding: book_research validates source text/hash before allocating evidence slots; current main validates after selection. This can recover valid lower-ranked evidence when stale candidates occupy the limit. Port this separately with adversarial tests. It is not merely a parallel-search PR.

All nine branches have commits on both sides of the baseline. No PR was merged, closed or approved. No user-facing accuracy/latency gains are inferred from merge checks.

## Outstanding repository operations

The public branch API reports main protected=false. The connected GitHub tools expose file/PR operations but no branch-protection write operation. Protection has NOT been enabled. Require PRs, current successful quality and Windows/Linux SQLCipher checks, block deletion/force pushes, and choose a review count compatible with available collaborators. Confirm exact check names after actual CI execution.
