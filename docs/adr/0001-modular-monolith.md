# ADR-0001 — Governed Modular Monolith for Offline-First EXPECTO

**Status:** Proposed (7.7 PR, not yet merged).
**Decision date:** 2026-11-03.

## Context

EXPECTO runs primarily on one local computer, may use 16 GB of RAM with
integrated graphics, and requires privacy-preserving, offline-capable
operation. Microservices would add interprocess RPC, operational overhead,
duplicated memory, failure modes and more sensitive transports.

## Decision

Maintain **one Python backend process** with clear modules and bounded,
per-instance services. Preserve one persistent SQLite/SQLCipher database.
Keep model inference, evidence retrieval and command authorization separate.
Treat information from PDFs, web content and previous memory as untrusted
data; model-generated text does not authorize tools.

Use narrow structural ports to allow optional providers, one scoped lazy
service registry, source-level architecture checks in CI, and independent
domain tests plus offline integration tests.

Do not introduce message brokers, mandatory vector servers, Kubernetes,
dynamic code execution or autonomous self-modification merely to appear
more complex.

## Consequences

**Positive:** low idle resource overhead, simpler installation, stable
migration path, inspectable code boundaries, improved test substitution.
**Trade-offs:** import graph discipline and constructor contracts must be
maintained; large legacy modules require incremental migration; single
backend process limits fault isolation.

## Evidence to revisit

Consider an isolated worker only when real local benchmarks show long-running
PDF study or inference demonstrably blocks the interactive assistant, and
only after measuring RAM pressure, interruption/cancellation and privacy.
