"""Conversation service — manages multi-turn threads and their lifecycle.

Handles thread creation, message retrieval, message submission, and
thread lifecycle (archive/delete). Threads are backed by the LangGraph
checkpointer bound to the agent graph.

Thread isolation: Access control by thread_id — the caller is responsible
for verifying that the requesting user/tenant owns the thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ThreadInfo:
    """Metadata about a conversation thread.

    Attributes:
        thread_id: Unique thread identifier.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-activity timestamp.
        message_count: Approximate number of messages in the thread.
        status: ``"active"``, ``"archived"``, or ``"deleted"``.
    """

    thread_id: str
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    status: str = "active"


@dataclass
class ThreadService:
    """Lightweight thread lifecycle manager.

    In P0 this is backed by the checkpointer's database. The checkpointer
    is the authoritative source for thread existence and message history.
    """

    # Simple in-memory registry of thread metadata for P0
    _threads: dict[str, ThreadInfo] = field(default_factory=dict)

    def create_thread(self, thread_id: str) -> ThreadInfo:
        """Register a new thread.

        Args:
            thread_id: Unique thread identifier.

        Returns:
            ThreadInfo for the new thread.

        Raises:
            ValueError: If the thread_id already exists.
        """
        if thread_id in self._threads:
            existing = self._threads[thread_id]
            if existing.status == "deleted":
                # Re-create a previously deleted thread
                pass
            else:
                raise ValueError(f"Thread already exists: {thread_id!r}")

        now = datetime.now(timezone.utc).isoformat()
        info = ThreadInfo(
            thread_id=thread_id,
            created_at=now,
            updated_at=now,
            message_count=0,
            status="active",
        )
        self._threads[thread_id] = info
        return info

    def get_thread(self, thread_id: str) -> ThreadInfo | None:
        """Return thread metadata, or None."""
        info = self._threads.get(thread_id)
        if info is None:
            return None
        if info.status == "deleted":
            return None
        return info

    def touch_thread(self, thread_id: str) -> bool:
        """Update the last-activity timestamp. Returns True if thread exists."""
        info = self._threads.get(thread_id)
        if info is None or info.status == "deleted":
            return False
        info.updated_at = datetime.now(timezone.utc).isoformat()
        info.message_count += 1
        return True

    def archive_thread(self, thread_id: str) -> bool:
        """Mark a thread as archived. Returns True if successful."""
        info = self._threads.get(thread_id)
        if info is None:
            return False
        info.status = "archived"
        return True

    def delete_thread(self, thread_id: str) -> bool:
        """Soft-delete a thread. Returns True if successful."""
        info = self._threads.get(thread_id)
        if info is None:
            return False
        info.status = "deleted"
        return True

    def list_active_threads(self) -> list[ThreadInfo]:
        """Return all active (non-deleted, non-archived) threads."""
        return [t for t in self._threads.values() if t.status not in ("deleted", "archived")]

    @property
    def active_count(self) -> int:
        """Number of active threads."""
        return len(self.list_active_threads())
