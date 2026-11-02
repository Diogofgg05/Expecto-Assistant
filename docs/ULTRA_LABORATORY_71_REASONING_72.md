# EXPECTO 7.1 Laboratory + 7.2 Reasoning Engine

Implemented as an opt-in extension of 7.0.6. Existing API paths, data schema,
private memory, UI and normal streaming remain compatible. No model download,
training, automatic profile change or live database migration occurs.

## Run on the actual Windows/Linux machine

Activate the existing virtual environment, then:

```sh
python -m pip install -r requirements-laboratory.txt
python -m scripts.benchmark_ultra71 --model qwen3:8b --output ultra71-results.json
```

Replace the example with the EXACT installed name from `ollama list`. The lab
checks `/api/tags` before testing. ECO/BALANCED/MAX use the existing NanoMemory
policy, including its low-memory emergency override. Optional candidate models:

```sh
python -m scripts.benchmark_ultra71 --model qwen3:8b --eco-model qwen3:4b --max-model qwen3:14b --review-model hermes3:8b --output ultra72-results.json
```

Names are examples, not a hardware recommendation. All must already be installed.
Reviewer must differ from every candidate; identical installed digests are refused.
With a reviewer, each profile is evaluated with raw and reviewed answers on the
same exercises. Default 35 exercises × 2 repetitions × 3 profiles = 210 responses;
reviewed evaluation adds another 210, each with up to 4 inference calls. It can take
considerable time on old hardware. Interrupting stops inference; completed rows
are checkpointed atomically after each response. Incomplete reports do not recommend.

A random seed is generated each run. `--seed 123` reproduces a corpus for diagnosis;
use a NEW seed after tuning. Templates are public; new instances are not evidence
that the model has never encountered equivalent problems. Gold answers stay in
the evaluator and are never sent to either model.

## What each response measures

- `calls[].prep_ms`: retrieval/context and payload preparation, before network I/O.
- `calls[].queue_ms`: time waiting for the application inference slot, separate.
- `calls[].ttft_ms`: first nonempty content chunk, including preparation, excluding queue.
  Thinking-only chunks do not count as visible output; chunks are not counted as tokens.
- `calls[].tokens_per_second`: Ollama `eval_count / eval_duration * 1e9`, not guessed
  from characters. Provider generation includes the backend's own token accounting.
- `total_ms`: complete experiment, including verification/revision when enabled.
- `first_visible_ms`: first draft content for raw mode; the full verification latency
  for reviewed mode, whose draft is withheld.
- `calls[].resources.sampled_peak_bytes`: application RSS, visible local Ollama RSS,
  and `/api/ps` loaded-model VRAM sampled every 500 ms. Null means unavailable.

Memory measurements are sampled absolute process/model values, not per-response
allocation deltas or guaranteed peaks. Ollama RSS includes visible local processes,
may count shared pages twice, and cannot account for hidden/container/remote servers.
VRAM covers ALL loaded models, not just this response. Unified GPU memory can overlap
RAM; do not sum them. Background work and other Ollama clients affect comparisons.
`probe_wall_ms` reports sampler wall time, not a subtraction from response latency.
ECO unloads with keep_alive=0m; warmup does NOT make every subsequent ECO call warm.
These are whole-policy comparisons, not isolated equal-cache microbenchmarks.

To collect resources in ordinary chat, set:

```dotenv
AURA_RESPONSE_RESOURCE_SAMPLING=true
```

Install `requirements-laboratory.txt` for psutil on Windows/Linux. Resource polling
is opt-in because it adds overhead; the lab always enables it. The existing local
`GET /api/performance/status` now returns the last 64 anonymous Ollama reply records
alongside aggregates. It stores no question, answer, source passage or private prompt.
Non-model interface commands do not have token statistics. Nonstreaming calls have
no observable TTFT and return null. Interrupted streams without `done` fail closed.

## Correctness before speed

Procedural families: exact 2×2 determinants, Python loop-output prediction with an
independent Python oracle (NO generated code executed), and synthetic source agreement
or contradiction. Each response is scored against an exact expected result. Strict
answer-format failures count as failures. Error and truncation runs remain in the
report; low-memory profile overrides are not silently scored as the requested profile.

A candidate needs matching cases/repetitions, at least 12 cases, two repetitions,
90% overall accuracy, 80% in every domain, no failed inference, and ZERO paired losses
on cases BALANCED/raw got right. Only then is the lowest median end-to-end latency
recommended as a **candidate for a local trial**. No settings are changed.

This is empirical non-regression on a small suite, NOT statistical proof of equal
accuracy and NOT a guarantee for unseen questions. RAM/VRAM are reported for review;
there is no claim of an optimal memory-constrained profile. Keep a separate new-seed
holdout after selecting a candidate. The programming family tests code tracing,
not generated programs against arbitrary functional tests. Research tasks test
source discipline, not the truth of open-world web claims.

## 7.2 reasoning in the application

`calcula: (123 + 7) * 3` uses the existing bounded rational evaluator, independently
of a language model. It accepts only a whole explicit expression. Arbitrary Python
is never evaluated. Unsupported mathematics continues through the normal path.

`resolve com verificação: <problem>` creates a proposal, inspects arithmetic
statements and Python syntax, then obtains an optional separate-model review.
A refuted answer gets at most ONE revision and must be checked again. Invalid JSON,
invented source IDs, unresolved objections and verification timeout cause abstention.
No provisional tokens are exposed before checking finishes. The overall verification
budget is 90 seconds. Syntax acceptance never means functional correctness.

```dotenv
AURA_REASONING_MATH_MODEL=qwen3:8b
AURA_REASONING_CODE_MODEL=qwen3:8b
AURA_REASONING_RESEARCH_MODEL=qwen3:8b
AURA_REASONING_REVIEW_MODEL=hermes3:8b
```

Specialist names are explicit choices, not assumed better models. Math/programming
fall back to the configured deep/main model when their specialist field is empty.
A missing configured specialist does not silently download or substitute a model.
Without a distinct reviewer, ordinary proposals are labelled unverified; research
verification abstains. Same-model/latest aliases are not independent review.
A distinct model's endorsement is labelled an OPINION, never mathematical proof;
different models can share training data and correlated mistakes.

The existing `investiga profundamente ...` command additionally checks its sourced
proposal when a review model is configured. The reviewer only sees the retrieved
passages; this does not introduce automatic web access. Citation validity alone does
not establish semantic support or truth. Private user passages remain on local Ollama.

## Validation boundary

Offline tests exercise paired quality gates, missing data, truncation, profile
fallback, resource cleanup, generated oracles, strict arithmetic, syntax rejection,
single revision, invalid citations, timeout, cancellation and independent-model labels.
Mocked Ollama tests are engineering checks, NOT performance or accuracy benchmarks.
Real Ollama was unavailable in the implementation environment: no measured model
speedup, accuracy improvement or recommended hardware profile is claimed.

Ollama API accounting reference: https://github.com/ollama/ollama/blob/main/docs/api.md

## Extended regression corpus

The generated suite now includes matrix multiplication, uniquely solvable linear
systems, function input/output contracts, dated superseding sources and instruction
injection distractors. Function contracts check predicted outputs; they do not yet
execute candidate implementations in a sandbox.

`failure_regressions` identifies incorrect cases, including proposals incorrectly
accepted by the reviewer. Reproduce them with the report seed and case ID. The
report deliberately does not retain model answer text, so manual inspection of
that text requires a future explicit diagnostic capture mode.

Save an initial report as baseline.json and retain its seed, model digests and
configuration. Repeat that seed after tuning, then evaluate a new seed to detect
overfitting. Do not interpret the same-seed comparison alone as general improvement.
