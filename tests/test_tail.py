from __future__ import annotations

import pytest

from csv_analyst.events import ProgressEvent
from csv_analyst.runner import tail_session
from tests.fakes import FakeSessionPlatform


@pytest.mark.asyncio
async def test_tail_deduplicates_history_against_stream() -> None:
    historical = {
        "id": "sevt_1",
        "type": "agent.message",
        "content": [{"type": "text", "text": "First"}],
    }
    live = {
        "id": "sevt_2",
        "type": "agent.message",
        "content": [{"type": "text", "text": "Second"}],
    }
    idle = {
        "id": "sevt_3",
        "type": "session.status_idle",
        "stop_reason": {"type": "end_turn"},
    }
    platform = FakeSessionPlatform([historical, live, idle])
    platform.history_events = [historical]
    platform.session_status = "running"
    received: list[ProgressEvent] = []
    await tail_session(platform, "sesn_fake", sink=received.append)
    assert [event.event_id for event in received] == ["sevt_1", "sevt_2", "sevt_3"]
    assert platform.calls == ["stream.open", "stream.close"]


@pytest.mark.asyncio
async def test_tail_prints_idle_history_and_exits() -> None:
    platform = FakeSessionPlatform()
    platform.history_events = [
        {
            "id": "sevt_1",
            "type": "agent.message",
            "content": [{"type": "text", "text": "Done"}],
        },
        {
            "id": "sevt_2",
            "type": "session.status_idle",
            "stop_reason": {"type": "end_turn"},
        },
    ]
    received: list[ProgressEvent] = []
    await tail_session(platform, "sesn_fake", sink=received.append)
    assert [event.event_id for event in received] == ["sevt_1", "sevt_2"]


@pytest.mark.asyncio
async def test_tail_drains_buffer_when_session_idles_after_history_snapshot() -> None:
    start = {"id": "sevt_1", "type": "session.status_running"}
    message = {
        "id": "sevt_2",
        "type": "agent.message",
        "content": [{"type": "text", "text": "Final answer"}],
    }
    usage = {
        "id": "sevt_3",
        "type": "session.usage",
        "usage": {"list_cost": {"amount": "7"}},
    }
    idle = {
        "id": "sevt_4",
        "type": "session.status_idle",
        "stop_reason": {"type": "end_turn"},
    }
    platform = FakeSessionPlatform([start, message, usage, idle])
    platform.history_events = [start]
    platform.session_status = "idle"
    received: list[ProgressEvent] = []
    await tail_session(platform, "sesn_fake", sink=received.append)
    assert [event.event_id for event in received] == [
        "sevt_1",
        "sevt_2",
        "sevt_3",
        "sevt_4",
    ]


@pytest.mark.asyncio
async def test_tail_second_history_read_catches_idle_transition() -> None:
    start = {"id": "sevt_1", "type": "session.status_running"}
    idle = {
        "id": "sevt_2",
        "type": "session.status_idle",
        "stop_reason": {"type": "end_turn"},
    }

    class AdvancingHistory(FakeSessionPlatform):
        def __init__(self) -> None:
            super().__init__([start, idle])
            self.reads = 0

        async def list_events(self, session_id: str) -> list[dict[str, object]]:
            self.reads += 1
            return [start] if self.reads == 1 else [start, idle]

    platform = AdvancingHistory()
    platform.session_status = "idle"
    received: list[ProgressEvent] = []
    await tail_session(platform, "sesn_fake", sink=received.append)
    assert [event.event_id for event in received] == ["sevt_1", "sevt_2"]
    assert platform.reads == 2
