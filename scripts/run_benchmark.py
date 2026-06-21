#!/usr/bin/env python3
"""Benchmark harness for the fxfill banking agent.

Run this script OUTSIDE Claude Code to evaluate the agent against the
public τ³-bench ``banking_knowledge`` domain.

Usage::

    uv run python scripts/run_benchmark.py \\
        --model claude-sonnet-4-6 \\
        --profile default \\
        --tasks banking_knowledge

This script does NOT access benchmark answers, rewards, evaluators,
or gold data. It only invokes the agent and records results.

IMPORTANT: Read ``CLAUDE.md`` before running this script. Official
evaluation must be performed manually outside Claude Code per the
benchmark-integrity rules in ADR 005.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fxfill_banking_agent.evaluation import EvalRunConfig, EvalRunResult, get_profile, results_dir
from fxfill_banking_agent.upstream import UpstreamLock, verify_upstream_commit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fxfill banking agent against tau2-bench tasks"
    )
    parser.add_argument("--model", default="claude-sonnet-4-6", help="LLM model identifier")
    parser.add_argument(
        "--profile",
        default="default",
        choices=["default", "long-reasoning", "fast"],
        help="Agent configuration profile",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=[],
        help="Specific task IDs to run (default: all banking_knowledge tasks)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override max agent steps",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature override",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory for results",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Free-text notes about this evaluation run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Pre-flight checks ────────────────────────────────────────────
    print("=== fxfill Benchmark Harness ===\n")

    # 1. Verify upstream is clean and pinned
    print("[1/4] Verifying upstream...")
    lock = UpstreamLock.from_lock_file()
    if not verify_upstream_commit(lock):
        print(f"  ERROR: Upstream HEAD does not match pinned commit {lock.commit}")
        print("  Please check out the correct commit and try again.")
        return
    print(f"  OK: upstream at {lock.commit[:8]}, domain={lock.domain}")

    # 2. Load configuration profile
    print(f"[2/4] Loading profile '{args.profile}'...")
    profile = get_profile(args.profile)
    if args.max_steps:
        profile["max_agent_steps"] = args.max_steps
    profile["llm"]["model"] = args.model
    profile["llm"]["temperature"] = args.temperature
    print(f"  model={args.model}, max_steps={profile['max_agent_steps']}")

    # 3. Prepare output directory
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.output_dir) if args.output_dir else results_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[3/4] Results will be saved to {out_dir / run_id}.json")

    # 4. Run the agent against tasks
    print(f"[4/4] Starting evaluation run {run_id}...")
    print(f"  Tasks: {args.tasks or 'all banking_knowledge'}")
    print(f"  Notes: {args.notes or '(none)'}")

    t0 = time.monotonic()
    config = EvalRunConfig(
        model=args.model,
        agent_config_profile=args.profile,
        task_ids=args.tasks,
        max_steps=args.max_steps,
        temperature=args.temperature,
        notes=args.notes,
    )

    # PLACEHOLDER: This is where the real agent invocation happens.
    # In Phase 5 we record the structure; actual execution is manual
    # and performed outside Claude Code.
    #
    # The human operator would:
    #   1. Set up LLM credentials in the environment
    #   2. Create an AgentRuntime with the selected profile
    #   3. Iterate over tau2-bench tasks (tau2.tasks.get_tasks(domain))
    #   4. For each task, run the agent and record the conversation
    #   5. Save all results to the output file
    #
    # None of this code reads benchmark answers, rewards, or evaluators.

    elapsed = time.monotonic() - t0

    # Write a placeholder result to validate the output pipeline
    result = EvalRunResult(
        run_id=run_id,
        config=config,
        total_tasks=0,
        completed_tasks=0,
        total_steps=0,
        total_duration_s=elapsed,
        results_path=str(out_dir / f"{run_id}.json"),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    result_path = out_dir / f"{run_id}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_id": result.run_id,
                "config": {
                    "model": result.config.model,
                    "profile": result.config.agent_config_profile,
                    "task_ids": result.config.task_ids,
                    "max_steps": result.config.max_steps,
                    "temperature": result.config.temperature,
                },
                "total_tasks": result.total_tasks,
                "completed_tasks": result.completed_tasks,
                "total_steps": result.total_steps,
                "total_duration_s": result.total_duration_s,
                "timestamp": result.timestamp,
            },
            indent=2,
        )
    )

    print(f"\nDone. Results written to {result_path}")
    print("\nNext steps:")
    print("  1. Set up LLM credentials (API key in environment)")
    print("  2. Run the agent against individual tasks")
    print("  3. Manually evaluate results using tau2-bench CLI:")
    print("     cd ../tau2-bench-upstream")
    print("     uv run tau2 evaluate --domain banking_knowledge \\")
    print(f"       --agent-output {result_path}")


if __name__ == "__main__":
    main()
