# ADR 005: Upstream as Read-Only Dependency

**Status:** Accepted  
**Date:** 2026-06-21

## Context

This project is evaluated against τ³-bench, an external benchmark
maintained by Sierra Research. Benchmark integrity requires that
we never modify upstream tasks, policies, evaluators, or data.
The upstream repository must be treated as a pinned, read-only
dependency — not a fork we can modify.

## Decision

**Treat the upstream repository as a read-only, pinned dependency.**

Concrete rules:

1. Pin the upstream commit in `UPSTREAM.lock`.
2. Verify the upstream checkout matches the pinned commit at
   development and CI time.
3. Never write to the upstream directory.
4. Never import evaluator internals, reference actions, expected
   outputs, or reward logic from the upstream package.
5. Run official benchmark evaluations manually outside Claude Code.
6. Development tests use repository-owned fixtures under `evals/dev/`,
   never benchmark answers.

Alternatives considered:

| Alternative | Rejected because |
|---|---|
| Fork the upstream repo | Breaks benchmarking comparability; creates merge debt |
| Git submodule | Adds complexity; pinned-path approach is simpler and explicit |
| Copy benchmark data into this repo | Risks stale data and accidental modification of test artifacts |

## Consequences

- Every developer must clone the upstream repo separately at the
  pinned path.
- `UPSTREAM.lock` is the single source of truth for the upstream version.
- Build and CI scripts verify the lock before any benchmark-adjacent work.
- The evaluation-integrity boundary is documented and auditable.
