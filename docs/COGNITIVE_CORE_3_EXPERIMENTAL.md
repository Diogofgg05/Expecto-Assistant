# Cognitive Core 3 — experimental scaffold

This is an isolated prototype, not a replacement for the existing reasoning orchestrator.

- Heuristic fast/deep router.
- Bounded retry attempts (maximum 3).
- Conservative evidence overlap signal; **never certifies semantic correctness**.
- Abstains without evidence.
- Does not execute external tools, write memory, train models or deploy itself.
- No benchmark score improvement is claimed.

Run: `python -m unittest tests.test_cognitive_core3`

Next: integrate independent claim-level semantic entailment with calibrated abstention; compare multiple candidate solutions; tool policies and sandbox; integrate with the existing orchestrator only after regression tests; evaluate on a held-out suite with real Ollama.
