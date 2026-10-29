# Expecto 6.0 — Software Chiplets

## Architecture

Borrow the **partitioning principle** from the AMD chiplet idea, not hardware
performance guarantees. Keep one Python process, one SQLite database, one
shared event loop; avoid creating a thread, process or HTTP service per module.

- **I/O die (analogy):** `aura/app.py` and `Database` own HTTP boundaries,
  persistence, security policy, and existing background tasks.
- **Compute chiplets:** fourteen existing services keep their public APIs.
  The fixed internal `AuraEngine._CHIPLET_CLASSES` manifest resolves each
  implementation only on first use.
- **Fabric:** `ChipletFabric` shares one instance per service, serialises
  first construction, detects cycles, and allows retry after failed factories.
- **Standby (power-gating analogy):** unused services are not constructed.
  Already initialised services remain resident until process termination.
- **Monitoring:** `GET /api/chiplets` or `estado dos chiplets` reports
  active and standby services, access counts, failures, and cold start times,
  without reading private content.

## Why this may help

1. Simple layout requests do not initialise Ollama, RAG, research or memory
   service objects.
2. The LLM always reuses one existing MemoryEngine.
3. Instances stay cached for warm requests, avoiding repeated construction.
4. No new process/queue is introduced and no additional polling is scheduled.

This version does **not** guarantee lower CPU, RAM or electricity consumption.
Module imports performed by DB migrations still happen and can dominate the
startup time. Ollama model RAM/VRAM is mostly outside this Python process.
Heavy inference, search, memory vector scans and prompt size remain separate
opportunities for future evidence-based optimisation.

## Run tests

```bash
python -m pytest -q tests/test_chiplets_v60.py tests/test_engine.py tests/test_api.py
```

Also run the rest of the offline suite before merging into main.

## Benchmarks and acceptance

Compare the same OS, hardware, Python version, dependencies and workload,
ideally 20 fresh-process runs each. Record startup p50/p95, peak RSS or
allocation traces, first-request latency, warm-request latency, CPU process
time, response correctness and error rate. No performance percentage should
be claimed without a reproducible A/B comparison against the main branch.

The optional benchmark script measures the *lazy vs forced eager construction*
within this version as a proxy, **not** a true comparison to previous commits.

## Security and compatibility

- No model-generated command can name/import a chiplet.
- No new API mutates components, secrets, permissions or the data model.
- No UI buttons, sidebars or pages.
- No automatic model fine-tuning or unrequested Internet use.
- Explicit user-authorised background research retains its existing behaviour.
- The class remains addressable through `engine.memory`, `engine.llm`, etc.

## Additional idle optimisations

- Memory daemon checks SQLite queues first and does not construct the
  embedding/extraction services until work exists. Disabled private capture
  still blocks all automatic processing as before.
- Hologram canvas redraw throttling is adaptive: roughly 15 fps in idle,
  20 fps while thinking, 30 fps while listening at a 60 Hz screen; reduced
  motion redraws at most 2 times per second. Real frame rates depend on
  browser scheduling and display refresh rate.
- Node VM tests simulate frames and validate idle/active/hidden budgets;
  they do not establish physical energy or GPU savings.
- The full Python suite also verifies pre-existing behaviour. Fixed the
  continuity suggestion ranking to respect **explicit user feedback** and
  explicitly recorded blockers, without executing suggested actions.
