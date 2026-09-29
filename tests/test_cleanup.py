from __future__ import annotations

import json
from pathlib import Path

import pytest

from csv_analyst.platform import OutputFileInfo
from csv_analyst.runner import cleanup_run
from tests.fakes import FakeSessionPlatform


def _summary(root: Path, *session_ids: str) -> None:
    directory = root / "run_1"
    directory.mkdir()
    (directory / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "sessions": [
                    {"session_id": session_id}
                    for session_id in (session_ids or ("sesn_fake",))
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_cleanup_archives_owned_idle_session(tmp_path: Path) -> None:
    _summary(tmp_path)
    platform = FakeSessionPlatform()
    outcomes = await cleanup_run(platform, "run_1", output_root=tmp_path)
    assert outcomes[0].action == "archived"
    assert "session.archive" in platform.calls
    assert "session.delete" not in platform.calls


@pytest.mark.asyncio
async def test_cleanup_never_touches_foreign_or_running_session(tmp_path: Path) -> None:
    _summary(tmp_path)
    platform = FakeSessionPlatform()
    platform.session_metadata = {"app": "someone-else", "run_id": "run_1"}
    outcomes = await cleanup_run(platform, "run_1", delete=True, output_root=tmp_path)
    assert outcomes[0].detail == "foreign metadata"
    platform.session_metadata = {"app": "csv-analyst", "run_id": "run_1"}
    platform.session_status = "running"
    outcomes = await cleanup_run(platform, "run_1", output_root=tmp_path)
    assert "user.interrupt" in outcomes[0].detail
    assert "session.archive" not in platform.calls
    assert "session.delete" not in platform.calls


@pytest.mark.asyncio
async def test_cleanup_delete_requires_every_output_locally(tmp_path: Path) -> None:
    _summary(tmp_path)
    platform = FakeSessionPlatform()
    names = ["report.md", "analysis.py", "manifest.json", "chart_01_a.png"]
    platform.output_schedule = [[OutputFileInfo(name, name) for name in names]]
    platform.history_events = [{"type": "user.message", "id": "sevt_1"}]
    destination = tmp_path / "run_1" / "tiny"
    destination.mkdir()
    (destination / "report.md").write_text("report", encoding="utf-8")
    outcomes = await cleanup_run(platform, "run_1", delete=True, output_root=tmp_path)
    assert outcomes[0].action == "skipped"
    assert "session.delete" not in platform.calls
    (destination / "analysis.py").write_text("print(1)", encoding="utf-8")
    (destination / "chart_01_a.png").write_bytes(b"PNG")
    (destination / "manifest.json").write_text(
        json.dumps({"charts": ["chart_01_a.png"]}), encoding="utf-8"
    )
    outcomes = await cleanup_run(platform, "run_1", delete=True, output_root=tmp_path)
    assert outcomes[0].action == "deleted"
    assert platform.calls.count("session.delete") == 1


@pytest.mark.asyncio
async def test_cleanup_delete_accepts_legacy_resume_artifacts(tmp_path: Path) -> None:
    _summary(tmp_path)
    platform = FakeSessionPlatform()
    names = ["report.md", "analysis.py", "manifest.json", "chart_01_a.png"]
    platform.output_schedule = [[OutputFileInfo(name, name) for name in names]]
    platform.history_events = [{"type": "user.message", "id": "sevt_1"}]
    legacy = tmp_path / "resumed-sesn_fake" / "tiny"
    legacy.mkdir(parents=True)
    (legacy / "report.md").write_text("report", encoding="utf-8")
    (legacy / "analysis.py").write_text("print(1)", encoding="utf-8")
    (legacy / "chart_01_a.png").write_bytes(b"PNG")
    (legacy / "manifest.json").write_text(
        json.dumps({"charts": ["chart_01_a.png"]}), encoding="utf-8"
    )
    outcomes = await cleanup_run(platform, "run_1", delete=True, output_root=tmp_path)
    assert outcomes[0].action == "deleted"


@pytest.mark.asyncio
async def test_cleanup_continues_after_previously_deleted_session(
    tmp_path: Path,
) -> None:
    _summary(tmp_path, "sesn_removed", "sesn_fake")
    platform = FakeSessionPlatform()
    platform.missing_sessions.add("sesn_removed")
    outcomes = await cleanup_run(platform, "run_1", output_root=tmp_path)
    assert [outcome.action for outcome in outcomes] == ["already_removed", "archived"]
    assert platform.calls == ["session.archive"]
