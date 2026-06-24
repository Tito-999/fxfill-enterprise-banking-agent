"""Unit tests for memory models and store."""

from __future__ import annotations

from fxfill_banking_agent.memory.models import (
    ConversationSummary,
    EpisodeRecord,
    MemoryPolicy,
    UserPreference,
)
from fxfill_banking_agent.memory.store import InMemoryMemoryStore


class TestUserPreference:
    def test_sensitive_key_blocked(self) -> None:
        pref = UserPreference(key="password", value="secret123")
        assert pref.is_sensitive_key

    def test_normal_key_allowed(self) -> None:
        pref = UserPreference(key="currency", value="USD")
        assert not pref.is_sensitive_key


class TestConversationSummary:
    def test_default_summary(self) -> None:
        s = ConversationSummary(user_goal="check balance")
        assert s.user_goal == "check balance"
        assert s.version == 1
        assert s.completed_actions == []

    def test_summary_with_facts(self) -> None:
        s = ConversationSummary(
            user_goal="send transfer",
            confirmed_facts={"account": "ACC-1001", "amount": 500},
            completed_actions=["created_draft"],
        )
        assert len(s.confirmed_facts) == 2
        assert "created_draft" in s.completed_actions


class TestEpisodeRecord:
    def test_episode_creation(self) -> None:
        ep = EpisodeRecord(
            episode_id="ep-1",
            intent="transfer_create",
            outcome="success",
            tool_count=3,
            duration_ms=1500.0,
        )
        assert ep.intent == "transfer_create"
        assert ep.outcome == "success"
        assert ep.tool_count == 3
        assert ep.tenant_id == "default"


class TestMemoryPolicy:
    def test_default_policy_blocks_pii(self) -> None:
        policy = MemoryPolicy()
        assert not policy.allow_pii
        assert not policy.allow_account_numbers

    def test_policy_limits(self) -> None:
        policy = MemoryPolicy(max_preferences_per_user=50, default_ttl_days=90)
        assert policy.max_preferences_per_user == 50
        assert policy.default_ttl_days == 90


class TestInMemoryStore:
    def test_save_and_get_preferences(self) -> None:
        store = InMemoryMemoryStore()
        pref = UserPreference(key="currency", value="USD", user_id="alice")
        assert store.save_preference(pref)

        prefs = store.get_preferences("alice")
        assert len(prefs) == 1
        assert prefs[0].value == "USD"

    def test_block_sensitive_preference(self) -> None:
        store = InMemoryMemoryStore()
        pref = UserPreference(key="password", value="secret", user_id="alice")
        assert not store.save_preference(pref)
        assert store.get_preferences("alice") == []

    def test_delete_preferences(self) -> None:
        store = InMemoryMemoryStore()
        store.save_preference(UserPreference(key="lang", value="en", user_id="alice"))
        store.delete_preferences("alice")
        assert store.get_preferences("alice") == []

    def test_save_episode(self) -> None:
        store = InMemoryMemoryStore()
        ep = EpisodeRecord(episode_id="ep-1", intent="transfer_create", tenant_id="t1")
        store.save_episode(ep)
        episodes = store.get_episodes("t1")
        assert len(episodes) == 1

    def test_tenant_isolation(self) -> None:
        store = InMemoryMemoryStore()
        store.save_preference(UserPreference(key="lang", value="en", user_id="a", tenant_id="t1"))
        store.save_preference(UserPreference(key="lang", value="fr", user_id="a", tenant_id="t2"))
        assert len(store.get_preferences("a", "t1")) == 1
        assert store.get_preferences("a", "t1")[0].value == "en"

    def test_health(self) -> None:
        import asyncio

        store = InMemoryMemoryStore()
        assert asyncio.run(store.health())
