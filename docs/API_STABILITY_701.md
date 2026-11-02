# EXPECTO 7.0.1 — API contracts & first stage of engine decomposition

This release focuses on correctness and a behavior-preserving structural refactor.

## HTTP / WebSocket contracts

- `GET /api/memory/status` remains the **personal-memory** status endpoint.
- `GET /api/resources/status` returns NanoMemory RAM policy and Ollama loaded-model
  accounting. The previous implementation accidentally registered two handlers
  for `/api/memory/status`, causing the second handler to be shadowed.
- `aura/api_contracts.py` checks all FastAPI HTTP method/path pairs and WebSocket
  paths. A future duplicate fails application creation rather than silently
  selecting the first handler.
- Tests cover route uniqueness, OpenAPI visibility, both status contracts,
  origin protection, malformed payloads and existing command routing.

## Main engine split

`aura/engine.py`: **855 → 582 lines** in the first low-risk extraction.

- `aura/command_reflection.py`: explicit feedback/reflection/goal commands
- `aura/command_research.py`: explicit user-triggered research commands
- `aura/engine_services.py`: panel projections, memory/index workers and
  autonomous opt-in research worker

The core still controls privilege boundaries and command order. The model
cannot initiate privileged actions from generated output, and the project
does not rewrite stored memory or migrate the database.

The engine is **not yet fully decomposed**: additional memory CRUD and
intent handlers remain inside the 582-line router. Future extractions
should be incremental and backed by regression tests.

## Validation

CI now attempts the **full Python test suite**, not only the selected voice
regression subset, plus JavaScript syntax, Node speech tests and Python
syntax. Optional external models (Ollama/Whisper/Piper) are not exercised
by these offline unit tests.

No benchmark claim is implied by splitting the module or fixing routes.
