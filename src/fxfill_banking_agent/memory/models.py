"""Memory models — typed structures for all memory layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ConversationSummary:
    """Structured compression of a long conversation.

    Used to keep context bounded while retaining key facts across many turns.
    """

    user_goal: str = ""
    confirmed_facts: dict[str, Any] = field(default_factory=dict)
    unresolved_questions: list[str] = field(default_factory=list)
    completed_actions: list[str] = field(default_factory=list)
    denied_actions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class UserPreference:
    """A single user preference safe for long-term storage.

    Only non-sensitive preferences are stored. Preferences never include
    account numbers, credentials, or transaction details.
    """

    key: str
    value: str
    user_id: str = ""
    tenant_id: str = "default"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_days: int = 365

    @property
    def is_sensitive_key(self) -> bool:
        """Check if the preference key is on the blocklist."""
        blocked = {"account_number", "password", "pin", "ssn", "token", "secret"}
        return self.key.lower() in blocked


@dataclass
class EpisodeRecord:
    """Anonymized summary of a completed task episode.

    Does NOT store: full account numbers, PII, raw tool arguments,
    or model private reasoning.
    """

    episode_id: str
    tenant_id: str = "default"
    intent: str = ""
    outcome: str = ""
    tool_count: int = 0
    duration_ms: float = 0.0
    anonymized_summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_days: int = 90


@dataclass
class MemoryPolicy:
    """Controls what information can enter each memory layer.

    Attributes:
        allow_pii: If True, PII can enter memory (default False).
        allow_account_numbers: If True, account numbers are stored.
        max_summary_length: Max characters for conversation summaries.
        max_preferences_per_user: Max stored preferences per user.
        default_ttl_days: Default time-to-live for new records.
    """

    allow_pii: bool = False
    allow_account_numbers: bool = False
    max_summary_length: int = 2000
    max_preferences_per_user: int = 50
    default_ttl_days: int = 90
