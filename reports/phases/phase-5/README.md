# Phase 5 — Benchmark Evaluation and Tuning

**Status:** COMPLETE (infrastructure ready)
**Date:** 2026-06-21

## Exit Criteria

| Criterion | Status | Detail |
|---|---|---|
| Evaluation profiles ready | ✅ PASS | 3 profiles: default, long-reasoning, fast |
| Benchmark harness script | ✅ PASS | `scripts/run_benchmark.py` |
| Result tracking | ✅ PASS | EvalRunConfig + EvalRunResult dataclasses |
| Configuration documented | ✅ PASS | Profile docs and CLI help |
| No benchmark internals accessed | ✅ PASS | Script reads tasks, never evaluators/rewards |
| Tests pass | ✅ PASS | 113 total (104 prior + 9 new) |
| Ruff passes | ✅ PASS | All checks passed |
| Mypy strict | ✅ PASS | No issues in 15 source files |

## New Files

| File | Purpose |
|---|---|
| `src/fxfill_banking_agent/evaluation.py` | Profiles, config, result types |
| `scripts/run_benchmark.py` | CLI harness for manual evaluation |
| `tests/unit/test_evaluation.py` | 9 tests (profiles, config, results) |

## Next Steps (Human Operator)

1. Set LLM API credentials in environment
2. Run: `uv run python scripts/run_benchmark.py --model claude-sonnet-4-6 --profile default`
3. Evaluate: `cd ../tau2-bench-upstream && uv run tau2 evaluate ...`
4. Iterate on configuration profiles based on results
