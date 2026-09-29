from __future__ import annotations

import json
from pathlib import Path

import pytest

from csv_analyst.runner import run_session
from tests.fakes import FakeSessionPlatform

EVENTS = Path(__file__).parent / "fixtures" / "events"


@pytest.mark.asyncio
async def test_runner_streams_before_send_and_records_cost(tmp_path: Path) -> None:
    path = tmp_path / "tiny.csv"
    path.write_text("x\n1\n", encoding="utf-8")
    events = [
        json.loads(line)
        for line in (EVENTS / "tiny_end_turn.jsonl").read_text().splitlines()
    ]
    platform = FakeSessionPlatform(events)
    seen = []

    result = await run_session(
        platform,
        path,
        "agent_1",
        "env_1",
        "run_1",
        budget_cents=50,
        timeout_s=10,
        sink=seen.append,
    )

    assert result.status == "completed"
    assert result.stop_reason == "end_turn"
    assert result.list_cost_cents == 3
    assert platform.budget_cents == 50
    assert platform.calls == [
        "upload",
        "session.create",
        "stream.open",
        "events.send_message",
        "stream.close",
    ]
    assert any(event.kind == "tool_use" for event in seen)


@pytest.mark.asyncio
async def test_runner_stops_on_budget_pause(tmp_path: Path) -> None:
    path = tmp_path / "tiny.csv"
    path.write_text("x\n1\n", encoding="utf-8")
    events = [
        json.loads(line)
        for line in (EVENTS / "budget_reached.jsonl").read_text().splitlines()
    ]
    result = await run_session(
        FakeSessionPlatform(events),
        path,
        "agent_1",
        "env_1",
        "run_1",
        budget_cents=5,
        timeout_s=10,
    )
    assert result.status == "paused_budget"
    assert result.list_cost_cents == 6


@pytest.mark.asyncio
async def test_runner_recovers_from_retrying_error(tmp_path: Path) -> None:
    path = tmp_path / "tiny.csv"
    path.write_text("x\n1\n", encoding="utf-8")
    events = [
        {"type": "session.status_running"},
        {
            "type": "session.error",
            "error": {
                "type": "model_rate_limited_error",
                "message": "Retrying automatically",
                "retry_status": {"type": "retrying"},
            },
        },
        {"type": "session.status_rescheduled"},
        {"type": "session.status_running"},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    seen = []

    result = await run_session(
        FakeSessionPlatform(events),
        path,
        "agent_1",
        "env_1",
        "run_1",
        budget_cents=50,
        timeout_s=10,
        sink=seen.append,
    )

    assert result.status == "completed"
    assert result.stop_reason == "end_turn"
    assert result.error_types == ("model_rate_limited_error",)
    assert any(event.kind == "error" for event in seen)
