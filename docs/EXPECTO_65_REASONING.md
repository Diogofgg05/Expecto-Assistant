# Expecto 6.5 — verified steps and bounded review

Goal: raise reasoning quality to a demonstrated **16/20**, not to a cosmetic label. The current score remains an estimate until independent, real-model evaluations pass. This branch integrates pre-existing exact algebra with the normal conversational route and adds a bounded revision pass for complex queries.

## Working code

- `aura/reasoning_runtime.py`: `exact_math_reply` recognizes narrowly specified 2–3 variable linear systems and square matrix determinant/inverse prompts. Unsupported/ambiguous questions continue to the existing Ollama route. The exact solver is deterministic, limited and uses Python rational arithmetic, not generated code.
- `arithmetic_audit`: checks up to eight explicit integer/fraction identities in the generated response. It can reject visibly incorrect arithmetic but does not prove all claims.
- `ReasoningRuntime`: for complex questions, asks the existing local primary Ollama model to review a draft; at most one repair. Invalid calculation => repaired response must pass recheck or a clear abstention is shown. The reviewer is the **same model**, not a factual independent judge.
- `aura/llm.py`: bounded review transport through the existing concurrency limiter. No new cloud backend or model installation. Review failures safely degrade without claiming verification.
- `aura/engine.py`: ordinary chat now delegates exact algebra to the solver when syntax is unambiguous. Other questions preserve LLM fallback; complex responses optionally receive a review.
- `GET /api/reasoning/status`: read-only counters, no saved prompts.

Configuration: `AURA_REASONING_REVIEW_MODE=balanced` (default) reviews complex tasks only, `off` disables review, and `deep` reviews all model responses. Higher review effort costs additional inference time and model tokens.

## Test criteria (mandatory before claiming 16/20)

1. Existing Python and Node regression suites pass.
2. Evaluate **at least 100 independent hidden problems**, with domain splits for mathematics, code, source-grounded QA, logic, contradictions and abstention. Questions must not be used in model prompts/training. Independent graded reference answers required.
3. Measure correctness, source fidelity, unsafe tool attempts, hallucination rate, proper abstention, p50/p95 latency, RAM and GPU memory **on real local Ollama hardware**.
4. Compare fixed baseline 6.4 to candidate 6.5 with identical model, seed, hardware and retrieval corpus. Only recommend 16/20 if correctness and robustness gates pass on an untouched final holdout and latency costs are acceptable.

The offline tests validate architecture and exact arithmetic, **not** broader model intelligence or a measured 16/20. RAG citations remain evidence pointers, not semantic proofs.

Inspired by quality gates and heterogeneous execution principles, but not copying proprietary code from Apple, AMD, or NVIDIA.
