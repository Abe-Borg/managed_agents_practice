from __future__ import annotations

import json
from pathlib import Path

import pytest

from csv_analyst.platform import OutputFileInfo
from csv_analyst.runner import ask_session
from tests.fakes import FakeSessionPlatform


@pytest.mark.asyncio
async def test_ask_rejects_running_session_before_sending(tmp_path: Path) -> None:
    platform = FakeSessionPlatform()
    platform.session_status = "running"
    with pytest.raises(ValueError, match="must be idle"):
        await ask_session(
            platform, "sesn_fake", "Summarize", timeout_s=10, output_root=tmp_path
        )
    assert "stream.open" not in platform.calls
    assert platform.sent_message is None


@pytest.mark.asyncio
async def test_ask_reuses_session_and_collects_numbered_outputs(tmp_path: Path) -> None:
    platform = FakeSessionPlatform(
        [
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
        ]
    )
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}
    ]
    names = [
        "followup_1_report.md",
        "followup_1_chart_01_region.png",
        "followup_1_manifest.json",
    ]
    platform.output_schedule = [[], [OutputFileInfo(name, name) for name in names]]
    platform.output_payloads = {
        "followup_1_report.md": b"# Region breakdown",
        "followup_1_chart_01_region.png": b"PNG",
        "followup_1_manifest.json": json.dumps({"files": names[:2]}).encode(),
    }
    result, files = await ask_session(
        platform,
        "sesn_fake",
        "Break revenue down by region with one chart",
        timeout_s=10,
        output_root=tmp_path,
    )
    assert result.status == "completed"
    assert {file.name for file in files} == set(names)
    assert all(file.parent == tmp_path / "run_1" / "tiny" for file in files)
    assert "/mnt/session/outputs/analysis.py" in (platform.sent_message or "")
    assert "followup_1_report.md" in (platform.sent_message or "")
    assert platform.calls.index("stream.open") < platform.calls.index(
        "events.send_message"
    )


@pytest.mark.asyncio
async def test_ask_rejects_budget_pause(tmp_path: Path) -> None:
    platform = FakeSessionPlatform()
    platform.history_events = [
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}}
    ]
    with pytest.raises(ValueError, match="raise-budget"):
        await ask_session(
            platform, "sesn_fake", "Why?", timeout_s=10, output_root=tmp_path
        )
    assert platform.sent_message is None
