"""Opt-in Phase 5 parallel and budget-resume checks."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

import pytest

from csv_analyst.agent_spec import build_agent_spec, build_environment_spec
from csv_analyst.config import load_settings
from csv_analyst.orchestrator import run_many
from csv_analyst.outputs import collect
from csv_analyst.platform import SdkPlatform, SdkSessionPlatform
from csv_analyst.resources import (
    SKILL_DIR,
    ensure_agent,
    ensure_environment,
    ensure_skill,
    load_state,
)
from csv_analyst.runner import resume_budget_session, run_session


def _resources() -> tuple[str, str, str]:
    settings = load_settings()
    if settings.api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY available")
    platform = SdkPlatform(settings.api_key)
    environment = ensure_environment(platform, build_environment_spec())
    if load_state().agent_id is None:
        ensure_agent(platform, build_agent_spec(settings))
    skill = ensure_skill(platform, SKILL_DIR)
    agent = ensure_agent(
        platform, build_agent_spec(settings, skill_id=skill.resource.id)
    )
    return settings.api_key, agent.resource.id, environment.resource.id


@pytest.mark.live_extra
def test_three_sessions_overlap_and_are_isolated(tmp_path: Path) -> None:
    if os.environ.get("CSV_ANALYST_LIVE_EXTRA") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE_EXTRA=1 for additional live calls")
    api_key, agent_id, environment_id = _resources()
    files = [
        Path("fixtures/sales.csv"),
        Path("fixtures/weather.csv"),
        Path("fixtures/web_traffic.csv"),
    ]
    summary = asyncio.run(
        run_many(
            files,
            lambda: SdkSessionPlatform(api_key),
            agent_id,
            environment_id,
            "live-parallel",
            budget_cents=100,
            timeout_s=600,
            max_parallel=3,
            output_root=tmp_path / "parallel",
        )
    )
    assert len(summary.sessions) == 3
    assert all(item.status == "completed" for item in summary.sessions)
    assert all(item.isolation is True for item in summary.sessions)
    assert len({item.session_id for item in summary.sessions}) == 3
    assert all(item.artifacts_path is not None for item in summary.sessions)
    starts = [datetime.fromisoformat(item.started_at) for item in summary.sessions]
    ends = [datetime.fromisoformat(item.ended_at) for item in summary.sessions]
    assert max(starts) < min(ends)
    print(f"parallel costs={[item.list_cost_cents for item in summary.sessions]}")


@pytest.mark.live_extra
def test_budget_pause_and_resume(tmp_path: Path) -> None:
    if os.environ.get("CSV_ANALYST_LIVE_EXTRA") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE_EXTRA=1 for additional live calls")
    api_key, agent_id, environment_id = _resources()

    async def execute() -> tuple[int | None, int | None]:
        platform = SdkSessionPlatform(api_key)
        try:
            first = await run_session(
                platform,
                Path("fixtures/sales.csv"),
                agent_id,
                environment_id,
                "live-budget",
                budget_cents=5,
                timeout_s=600,
            )
            assert first.status == "paused_budget", first
            resumed = await resume_budget_session(
                platform, first.session_id, 100, timeout_s=600
            )
            assert resumed.status == "completed", resumed
            outputs = await collect(
                platform, first.session_id, tmp_path / "resumed", "sales.csv"
            )
            assert (outputs.directory / "manifest.json").is_file()
            return first.list_cost_cents, resumed.list_cost_cents
        finally:
            await platform.close()

    before, after = asyncio.run(execute())
    print(f"budget costs before={before} after={after}")
