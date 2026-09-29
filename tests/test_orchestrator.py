from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from csv_analyst.orchestrator import check_isolation, run_many
from csv_analyst.platform import OutputFileInfo, SessionInfo
from tests.fakes import FakeSessionPlatform


class ParallelFake(FakeSessionPlatform):
    def __init__(
        self, session_id: str, events: list[dict[str, Any]], *, fail: bool = False
    ) -> None:
        super().__init__(events)
        self.session_id = session_id
        self.fail = fail

    async def upload_file(self, path: Path) -> str:
        if self.fail:
            raise RuntimeError("upload failed")
        return await super().upload_file(path)

    async def create_session(
        self,
        agent_id: str,
        environment_id: str,
        file_id: str,
        input_name: str,
        budget_cents: int | None,
        run_id: str,
        *,
        agent_version: int | None = None,
        model: str | None = None,
    ) -> SessionInfo:
        base = await super().create_session(
            agent_id, environment_id, file_id, input_name,
            budget_cents, run_id, agent_version=agent_version, model=model,
        )
        return replace(base, id=self.session_id)


@pytest.mark.asyncio
async def test_three_outcomes_survive_one_failure(tmp_path: Path) -> None:
    files = [tmp_path / f"{name}.csv" for name in ("a", "b", "c")]
    for file in files:
        file.write_text("x\n1\n", encoding="utf-8")
    complete = [
        {"type": "session.usage", "usage": {
            "list_cost": {"amount": "3"}, "active_seconds": 2.5
        }},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    paused = [
        {"type": "session.usage", "usage": {"list_cost": {"amount": "6"}}},
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}},
    ]
    platforms = [
        ParallelFake("sesn_a", complete),
        ParallelFake("sesn_b", paused),
        ParallelFake("sesn_c", [], fail=True),
    ]
    names = ["report.md", "analysis.py", "chart_01_values.png", "manifest.json"]
    platforms[0].output_schedule = [
        [OutputFileInfo(name, name) for name in names]
    ]
    platforms[0].output_payloads = {
        "report.md": b"# report",
        "analysis.py": b"print(1)",
        "chart_01_values.png": b"\x89PNG\r\n\x1a\n",
        "manifest.json": json.dumps({
            "input_file": "a.csv", "uploads_seen": ["a.csv"],
            "markers_seen_before_write": [], "exclusive_marker_created": True,
            "rows": 1, "columns": 1, "charts": ["chart_01_values.png"],
            "summary": "a", "skill_used": True,
        }).encode(),
    }
    iterator = iter(platforms)
    summary = await run_many(
        files, lambda: next(iterator), "agent", "env", "run",
        budget_cents=5, timeout_s=10, max_parallel=3,
        output_root=tmp_path / "runs",
    )
    assert [item.status for item in summary.sessions] == [
        "completed", "paused_budget", "failed"
    ]
    assert summary.sessions[0].isolation is True
    assert summary.sessions[0].active_seconds == 2.5
    assert summary.sessions[1].list_cost_cents == 6
    assert summary.total_list_cost_cents == 9
    assert (tmp_path / "runs" / "summary.json").is_file()
    assert all("platform.close" in platform.calls for platform in platforms)


def test_isolation_checks_exclusive_marker_and_uploads() -> None:
    manifest = {
        "input_file": "a.csv", "uploads_seen": ["a.csv"],
        "markers_seen_before_write": [], "exclusive_marker_created": True,
    }
    assert check_isolation(manifest, "a.csv")
    assert not check_isolation({**manifest, "uploads_seen": ["a.csv", "b.csv"]}, "a.csv")
    assert not check_isolation({**manifest, "exclusive_marker_created": False}, "a.csv")


@pytest.mark.asyncio
async def test_same_stems_rejected_before_sessions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="distinct"):
        await run_many(
            [tmp_path / "x.csv", tmp_path / "x.CSV"],
            FakeSessionPlatform, "agent", "env", "run",
            budget_cents=5, timeout_s=10, max_parallel=3,
            output_root=tmp_path / "runs",
        )


@pytest.mark.asyncio
async def test_semaphore_limits_active_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import csv_analyst.orchestrator as orchestrator
    from csv_analyst.runner import SessionResult

    current = 0
    peak = 0

    async def fake_run(
        platform: FakeSessionPlatform, path: Path, *_args: object,
        **_kwargs: object,
    ) -> SessionResult:
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.01)
        current -= 1
        return SessionResult(
            path.stem, "paused_budget", "budget_reached", 5, ()
        )

    monkeypatch.setattr(orchestrator, "run_session", fake_run)
    files = [tmp_path / f"{name}.csv" for name in ("a", "b", "c")]
    summary = await run_many(
        files, FakeSessionPlatform, "agent", "env", "run",
        budget_cents=5, timeout_s=10, max_parallel=2,
        output_root=tmp_path / "runs",
    )
    assert peak == 2
    assert len(summary.sessions) == 3
