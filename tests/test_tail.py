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
