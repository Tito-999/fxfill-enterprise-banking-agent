"""Evaluation configuration and result tracking.

This module defines the shape of evaluation results but does NOT
import or access benchmark evaluators, reference actions, expected
outputs, reward functions, or gold database states.

Official evaluation is run manually outside Claude Code per the
benchmark-integrity rules documented in ADR 005.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalRunConfig:
    """Configuration for a benchmark evaluation run.

    Attributes:
        model: LLM model identifier.
        agent_config_profile: Name of the AgentConfig profile to use.
        task_ids: Specific task IDs to run (empty = all).
        max_steps: Override for agent max steps.
        temperature: Override for LLM temperature.
        notes: Free-text notes about this run.
    """

    model: str
    agent_config_profile: str = "default"
    task_ids: list[str] = field(default_factory=list)
    max_steps: int | None = None
    temperature: float = 0.0
    notes: str = ""


@dataclass
class EvalRunResult:
    """Results of a single benchmark evaluation run.

    Attributes:
        run_id: Unique identifier.
        config: The configuration used.
        total_tasks: Number of tasks evaluated.
        completed_tasks: Number of tasks that completed without error.
        total_steps: Total agent steps across all tasks.
        total_duration_s: Total wall-clock duration in seconds.
        results_path: Path to the raw results file.
        timestamp: ISO-8601 timestamp of the run.
    """

    run_id: str
    config: EvalRunConfig
    total_tasks: int
    completed_tasks: int
    total_steps: int
    total_duration_s: float
    results_path: str
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Configuration profiles for evaluation
# ---------------------------------------------------------------------------


def default_profile() -> dict[str, Any]:
    """Return the default evaluation agent configuration."""
    from fxfill_banking_agent.config import AgentConfig

    cfg = AgentConfig()
    return {
        "environment": cfg.environment.value,
        "max_agent_steps": cfg.max_agent_steps,
        "human_approval_required": cfg.human_approval_required,
        "llm": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.0,
            "max_tokens": 4096,
        },
    }


def long_reasoning_profile() -> dict[str, Any]:
    """Profile with more steps and higher temperature for complex tasks."""
    return {
        **default_profile(),
        "max_agent_steps": 100,
        "llm": {
            "provider": "anthropic",
            "model": "claude-opus-4-8",
            "temperature": 0.0,
            "max_tokens": 8192,
        },
    }


def fast_profile() -> dict[str, Any]:
    """Minimal configuration for quick smoke tests."""
    return {
        **default_profile(),
        "max_agent_steps": 20,
        "llm": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "temperature": 0.0,
            "max_tokens": 2048,
        },
    }


EVAL_PROFILES: dict[str, dict[str, Any]] = {
    "default": default_profile(),
    "long-reasoning": long_reasoning_profile(),
    "fast": fast_profile(),
}


def get_profile(name: str) -> dict[str, Any]:
    """Return a named evaluation profile.

    Args:
        name: Profile name (``"default"``, ``"long-reasoning"``, ``"fast"``).

    Returns:
        The profile dict.

    Raises:
        KeyError: If the profile name is unknown.
    """
    if name not in EVAL_PROFILES:
        raise KeyError(f"Unknown profile: {name!r}. Available: {list(EVAL_PROFILES)}")
    return EVAL_PROFILES[name]


def results_dir() -> Path:
    """Return the directory for evaluation results."""
    path = Path("artifacts/eval-results")
    path.mkdir(parents=True, exist_ok=True)
    return path
