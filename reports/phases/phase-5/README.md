# Phase 5 — Evaluation Harness and Synthetic Validation

**Status:** Evaluation harness implemented and validated with deterministic
synthetic fixtures. No official tau2-bench evaluation has been executed.
**Date:** 2026-06-21

## Exit Criteria

| Criterion | Status | Detail |
|---|---|---|
| Evaluation profiles ready | ✅ PASS | 3 profiles: default, long-reasoning, fast |
| Benchmark harness script | ✅ SCAFFOLD | `scripts/run_benchmark.py` contains placeholder-result path |
| Result tracking | ✅ PASS | EvalRunConfig + EvalRunResult dataclasses |
| No benchmark internals accessed | ✅ PASS | Never imports evaluators, rewards, or gold data |
| Synthetic tests pass | ✅ PASS | 9 profile/config tests with deterministic fixtures |
| Ruff passes | ✅ PASS | All checks passed |
| Mypy strict | ✅ PASS | No issues in source files |

## Important

**No official tau2-bench evaluation has been executed.** The placeholder
in `scripts/run_benchmark.py` stores a synthetic result to validate the
output pipeline. It must not be presented as a real benchmark result.

Official evaluation is manual outside Claude Code per ADR 005.

## New Files

| File | Purpose |
|---|---|
| `src/fxfill_banking_agent/evaluation.py` | Profiles, config, result types |
| `scripts/run_benchmark.py` | CLI harness for manual evaluation |
| `tests/unit/test_evaluation.py` | 9 tests (profiles, config, results) |

## Manual Evaluation Procedure (Human Operator)

1. Set LLM API credentials in environment
2. Run: `uv run python scripts/run_benchmark.py --model claude-sonnet-4-6 --profile default`
3. Evaluate: `cd ../tau2-bench-upstream && uv run tau2 evaluate ...`
4. Iterate on configuration profiles based on results
