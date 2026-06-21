"""Tests for evaluation configuration."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.evaluation import (
    EVAL_PROFILES,
    EvalRunConfig,
    EvalRunResult,
    get_profile,
    results_dir,
)


class TestProfiles:
    def test_default_profile_exists(self) -> None:
        cfg = get_profile("default")
        assert cfg["max_agent_steps"] == 50
        assert cfg["llm"]["model"] == "claude-sonnet-4-6"

    def test_long_reasoning_profile(self) -> None:
        cfg = get_profile("long-reasoning")
        assert cfg["max_agent_steps"] == 100
        assert cfg["llm"]["max_tokens"] == 8192

    def test_fast_profile(self) -> None:
        cfg = get_profile("fast")
        assert cfg["max_agent_steps"] == 20
        assert cfg["llm"]["max_tokens"] == 2048

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown profile"):
            get_profile("nonexistent")

    def test_all_profiles_have_required_keys(self) -> None:
        for name in EVAL_PROFILES:
            cfg = get_profile(name)
            assert "environment" in cfg
            assert "max_agent_steps" in cfg
            assert "llm" in cfg
            assert "model" in cfg["llm"]


class TestEvalRunConfig:
    def test_defaults(self) -> None:
        cfg = EvalRunConfig(model="test-model")
        assert cfg.model == "test-model"
        assert cfg.agent_config_profile == "default"
        assert cfg.task_ids == []
        assert cfg.temperature == 0.0
        assert cfg.notes == ""

    def test_custom(self) -> None:
        cfg = EvalRunConfig(
            model="claude-opus-4-8",
            agent_config_profile="long-reasoning",
            task_ids=["t1", "t2"],
            max_steps=80,
            temperature=0.5,
            notes="test run",
        )
        assert cfg.task_ids == ["t1", "t2"]
        assert cfg.max_steps == 80


class TestEvalRunResult:
    def test_creation(self) -> None:
        cfg = EvalRunConfig(model="m")
        result = EvalRunResult(
            run_id="r1",
            config=cfg,
            total_tasks=10,
            completed_tasks=9,
            total_steps=45,
            total_duration_s=120.5,
            results_path="/tmp/results.json",
            timestamp="2026-06-21T00:00:00Z",
        )
        assert result.total_tasks == 10
        assert result.completed_tasks == 9


class TestResultsDir:
    def test_returns_path(self) -> None:
        path = results_dir()
        assert "artifacts" in str(path)
        assert "eval-results" in str(path)
