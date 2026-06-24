"""Memory system — working, summary, semantic, and episodic layers.

Memory layers:
- Working: Current thread messages, plan, tool results, approval state (in checkpoint)
- Summary: Structured compression of long conversations
- Semantic: User preferences that are safe to persist long-term
- Episodic: Anonymized task summaries for future reference

Security: All memory content is untrusted. Sensitive fields are never
persisted to semantic memory. Prompt injection content is filtered before
storage. Memory is tenant/user-isolated.
"""

from fxfill_banking_agent.memory.models import (
    ConversationSummary,
    EpisodeRecord,
    MemoryPolicy,
    UserPreference,
)

__all__ = [
    "ConversationSummary",
    "UserPreference",
    "EpisodeRecord",
    "MemoryPolicy",
]
