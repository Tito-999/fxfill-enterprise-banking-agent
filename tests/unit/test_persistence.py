"""Tests for event persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from fxfill_banking_agent.persistence import (
    AgentEvent,
    EventKind,
    SqliteEventStore,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_events.db"


@pytest.mark.asyncio
async def test_insert_and_query_run(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    await store.connect()

    event = AgentEvent(
        run_id="run-1",
        seq=0,
        kind=EventKind.USER_MESSAGE,
        payload={"content": "hello"},
    )
    await store.insert(event)

    events = await store.query_run("run-1")
    assert len(events) == 1
    assert events[0].kind == EventKind.USER_MESSAGE
    assert events[0].payload == {"content": "hello"}

    await store.close()


@pytest.mark.asyncio
async def test_multiple_events_ordered(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    await store.connect()

    for i, kind in enumerate(
        [
            EventKind.USER_MESSAGE,
            EventKind.AGENT_MESSAGE,
            EventKind.TOOL_CALL,
            EventKind.TOOL_RESULT,
        ]
    ):
        await store.insert(AgentEvent(run_id="r1", seq=i, kind=kind, payload={"n": i}))

    events = await store.query_run("r1")
    assert len(events) == 4
    assert [e.seq for e in events] == [0, 1, 2, 3]

    await store.close()


@pytest.mark.asyncio
async def test_query_filter_by_kind(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    await store.connect()

    await store.insert(AgentEvent(run_id="r1", seq=0, kind=EventKind.USER_MESSAGE, payload={}))
    await store.insert(
        AgentEvent(run_id="r1", seq=1, kind=EventKind.ERROR, payload={"msg": "fail"})
    )
    await store.insert(
        AgentEvent(run_id="r2", seq=0, kind=EventKind.ERROR, payload={"msg": "fail2"})
    )

    errors = await store.query(kind=EventKind.ERROR)
    assert len(errors) == 2

    await store.close()


@pytest.mark.asyncio
async def test_query_filter_by_run(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    await store.connect()

    await store.insert(AgentEvent(run_id="a", seq=0, kind=EventKind.USER_MESSAGE, payload={}))
    await store.insert(AgentEvent(run_id="b", seq=0, kind=EventKind.USER_MESSAGE, payload={}))

    a_events = await store.query(run_id="a")
    assert len(a_events) == 1

    await store.close()


@pytest.mark.asyncio
async def test_not_connected_raises(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    with pytest.raises(RuntimeError, match="not connected"):
        await store.insert(AgentEvent(run_id="x", seq=0, kind=EventKind.ERROR, payload={}))


@pytest.mark.asyncio
async def test_unique_constraint_enforced(db_path: Path) -> None:
    store = SqliteEventStore(db_path)
    await store.connect()

    await store.insert(AgentEvent(run_id="r1", seq=0, kind=EventKind.USER_MESSAGE, payload={}))
    with pytest.raises(Exception):  # IntegrityError
        await store.insert(AgentEvent(run_id="r1", seq=0, kind=EventKind.AGENT_MESSAGE, payload={}))

    await store.close()
