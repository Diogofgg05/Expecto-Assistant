# EXPECTO 7.0.6 — API, installation matrix and GitHub protection

## API

The same endpoint methods and paths are now registered by five modules:
- `aura/api_routes_commands.py`: health, standard commands, bounded streaming.
- `aura/api_routes_voice.py`: local audio and continuous WebSocket.
- `aura/api_routes_memory.py`: memory, episodes, timeline and consolidation.
- `aura/api_routes_knowledge.py`: learning, fact checking and audits.
- `aura/api_routes_system.py`: resource metrics, settings, web UI.

`aura/app.py` retains FastAPI creation, localhost origin checks,
TrustedHost middleware, private storage and background workers. Existing
`from aura.app import create_app`, `Message`, and `VoiceText` imports
are preserved. No database or vector migration.

## SQLCipher installation validation

New `.github/workflows/sqlcipher-install-matrix.yml` tests the actual
platform installers on `windows-latest` and `ubuntu-latest`, using Python
3.12. It installs the production `requirements.txt` (including a real
`sqlcipher3` wheel), verifies `PRAGMA cipher_version`, and runs the
encrypted migration/backup and Database façade regressions. Unlike ordinary
unencrypted unit-test CI, these jobs must fail if the SQLCipher driver
does not work. No model download or credentials are needed.

Windows `install_windows.bat --ci` is non-interactive and uses Python
3.12 when available, but interactive `install_windows.bat` still pauses
as before. Existing `install_linux.sh` runs directly.

The quality workflow now runs for every PR and every push to main; to
enforce protection, configure the repository settings below.

## Protect the main branch (owner/admin UI action required)

The GitHub connector used for this work can inspect the branch and
modify files/PRs, **but does not provide a branch-rule write operation**.
As a result branch protection is not claimed as configured.

On the GitHub repository:
1. Settings → Rules → Rulesets → New branch ruleset, or Settings → Branches
   → Add branch protection rule.
2. Target `main`; block force pushes and deletion.
3. Require a pull request before merging and at least one approving review.
   For a single-maintainer repository, choose a review policy compatible
   with actual collaborator availability.
4. Require these checks to pass:
   - `checks` from EXPECTO quality gate
   - `SQLCipher install (ubuntu-latest, Python 3.12)`
   - `SQLCipher install (windows-latest, Python 3.12)`
   Check exact names on the Actions UI before saving.
5. Require branches to be up to date; disallow bypass except for a
   documented break-glass emergency procedure.

Ruleset enforceability may depend on the repository ownership/plan and
settings; GitHub will show whether the rule is active.

## Audit of the nine previously open PRs

Compared all heads against `main` after 7.0.5. Every branch was **diverged**
(heads both ahead and behind main), so **do not merge blindly**. Unique
features must be ported as small cherry-picks or new PRs with current tests.

| PR | Theme | Recommendation |
|---|---|---|
| #10 | Parallel SearXNG latency | Benchmark search and cherry-pick focused concurrent code only |
| #8 | Fast voice/media | Extract audio/UX improvements, retest interruption and WebSocket security |
| #7 | Offline microphone/diagnostics | Prioritize remaining microphone failure fixes; avoid older API replacement |
| #6 | Windows SQLCipher installer | Compare installer behavior with new native CI; avoid copying older unrelated modules |
| #5 | Reasoning/RAG hardening | Isolate useful security checks, validate with adversarial tests |
| #4 | Exact algebra/reasoning | Port verifier tests and only measurable reasoning improvements |
| #3 | Adaptive compute | Compare routing with existing 7.0.5 profiles; avoid parallel implementation |
| #2 | Software chiplets | Review lifecycle/performance proposals, avoid duplicate services |
| #1 | Cognitive Core 3 scaffold | Keep experimental until quality/latency benchmarks demonstrate benefit |

No old PR was merged or closed automatically because divergent branches
contain changes not confirmed to be superseded.

## Validation limitations

API refactoring and CI do not demonstrate performance gains; they reduce
maintenance risk. CI tests real SQLCipher in hosted Windows/Linux systems,
not the user's own computer or all architectures. Keep encrypted backups
before upgrading a live installation.
