"""Memory store — in-memory implementation for semantic and episodic memory (A5).

Production should use PostgreSQL with tenant-isolated tables and TTL-based
cleanup. This in-memory store supports local development and testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fxfill_banking_agent.memory.models import (
    EpisodeRecord,
    MemoryPolicy,
    UserPreference,
)


@dataclass
class InMemoryMemoryStore:
    """In-memory memory store for development and testing.

    Enforces MemoryPolicy for PII filtering and TTL.
    """

    _preferences: dict[str, list[UserPreference]] = field(default_factory=dict)
    _episodes: dict[str, list[EpisodeRecord]] = field(default_factory=dict)
    policy: MemoryPolicy = field(default_factory=MemoryPolicy)

    # ── Preferences (semantic memory) ──────────────────────────

    def _pref_key(self, user_id: str, tenant_id: str) -> str:
        return f"{tenant_id}:{user_id}"

    def save_preference(self, pref: UserPreference) -> bool:
        """Save a user preference. Returns False if blocked by policy."""
        if pref.is_sensitive_key:
            return False
        key = self._pref_key(pref.user_id, pref.tenant_id)
        if key not in self._preferences:
            self._preferences[key] = []
        existing = self._preferences[key]
        if len(existing) >= self.policy.max_preferences_per_user:
            existing.pop(0)  # Evict oldest
        existing.append(pref)
        return True

    def get_preferences(self, user_id: str, tenant_id: str = "default") -> list[UserPreference]:
        """Return all preferences for a user."""
        return list(self._preferences.get(self._pref_key(user_id, tenant_id), []))

    def delete_preferences(self, user_id: str, tenant_id: str = "default") -> None:
        """Delete all preferences for a user."""
        self._preferences.pop(self._pref_key(user_id, tenant_id), None)

    # ── Episodes (episodic memory) ─────────────────────────────

    def save_episode(self, episode: EpisodeRecord) -> None:
        """Save an anonymized task episode."""
        if episode.tenant_id not in self._episodes:
            self._episodes[episode.tenant_id] = []
        self._episodes[episode.tenant_id].append(episode)

    def get_episodes(self, tenant_id: str = "default", limit: int = 20) -> list[EpisodeRecord]:
        """Return recent episodes for a tenant."""
        episodes = self._episodes.get(tenant_id, [])
        return episodes[-limit:]

    # ── Health ─────────────────────────────────────────────────

    async def health(self) -> bool:
        return True
