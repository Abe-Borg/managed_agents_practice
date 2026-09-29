from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

import csv_analyst.cli as cli_module
from csv_analyst.cli import app
from csv_analyst.platform import OutputFileInfo, SdkSessionPlatform
from csv_analyst.runner import resume_budget_session
from tests.fakes import FakeSessionPlatform


@pytest.mark.asyncio
async def test_raise_budget_requires_room_above_consumed_cost() -> None:
    platform = FakeSessionPlatform()
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}}
    ]
    with pytest.raises(ValueError, match="more than one cent"):
        await resume_budget_session(platform, "sesn_fake", 7, timeout_s=10)
    assert platform.updated_budget is None


@pytest.mark.asyncio
async def test_raise_budget_updates_then_streams_without_message() -> None:
    platform = FakeSessionPlatform(
        [
            {
                "type": "session.usage",
                "usage": {"list_cost": {"amount": "21"}, "active_seconds": 4.5},
            },
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
        ]
    )
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}}
    ]
    result = await resume_budget_session(platform, "sesn_fake", 100, timeout_s=10)
    assert result.status == "completed"
    assert result.list_cost_cents == 21
    assert result.active_seconds == 4.5
    assert platform.updated_budget == 100
    assert platform.calls == ["stream.open", "session.update_budget", "stream.close"]


@pytest.mark.asyncio
async def test_raise_budget_rejects_non_budget_pause() -> None:
    platform = FakeSessionPlatform()
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}
    ]
    with pytest.raises(ValueError, match="not paused"):
        await resume_budget_session(platform, "sesn_fake", 100, timeout_s=10)


@pytest.mark.asyncio
async def test_sdk_budget_update_body() -> None:
    update = AsyncMock()
    platform = object.__new__(SdkSessionPlatform)
    platform._client = SimpleNamespace(
        beta=SimpleNamespace(sessions=SimpleNamespace(update=update))
    )
    await platform.update_session_budget("sesn_123", 100)
    update.assert_awaited_once_with(
        "sesn_123",
        budget={
            "type": "limit",
            "max_list_cost": {"amount": "100", "currency": "USD"},
        },
    )


def test_raise_budget_collects_into_original_run_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-cli-test")
    platform = FakeSessionPlatform(
        [{"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}]
    )
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}}
    ]
    names = ["report.md", "analysis.py", "manifest.json", "chart_01_a.png"]
    platform.output_schedule = [[OutputFileInfo(name, name) for name in names]]
    platform.output_payloads = {
        "report.md": b"# Report",
        "analysis.py": b"print(1)",
        "chart_01_a.png": b"PNG",
        "manifest.json": json.dumps(
            {
                "input_file": "tiny.csv",
                "uploads_seen": ["tiny.csv"],
                "markers_seen_before_write": [],
                "rows": 1,
                "columns": 1,
                "charts": ["chart_01_a.png"],
                "summary": "tiny",
                "skill_used": True,
            }
        ).encode(),
    }
    monkeypatch.setattr(cli_module, "SdkSessionPlatform", lambda _key: platform)
    result = CliRunner().invoke(app, ["raise-budget", "sesn_fake", "--to-cents", "100"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "runs" / "run_1" / "tiny" / "report.md").is_file()
    assert not (tmp_path / "runs" / "resumed-sesn_fake").exists()
