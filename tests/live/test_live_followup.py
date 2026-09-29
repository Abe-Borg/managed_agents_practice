"""Opt-in, budgeted checkpoint, reconnect, and archive check."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from csv_analyst.agent_spec import build_agent_spec, build_environment_spec
from csv_analyst.config import load_settings
from csv_analyst.outputs import collect
from csv_analyst.platform import SdkPlatform, SdkSessionPlatform
from csv_analyst.resources import (
    SKILL_DIR,
    ensure_agent,
    ensure_environment,
    ensure_skill,
    load_state,
)
from csv_analyst.runner import ask_session, cleanup_run, run_session, tail_session


@pytest.mark.live_extra
def test_followup_uses_checkpoint_and_archives(tmp_path: Path) -> None:
    if os.environ.get("CSV_ANALYST_LIVE_EXTRA") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE_EXTRA=1 for additional live calls")
    settings = load_settings()
    if settings.api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY available")
    setup = SdkPlatform(settings.api_key)
    environment = ensure_environment(setup, build_environment_spec())
    if load_state().agent_id is None:
        ensure_agent(setup, build_agent_spec(settings))
    skill = ensure_skill(setup, SKILL_DIR)
    agent = ensure_agent(setup, build_agent_spec(settings, skill_id=skill.resource.id))

    async def execute() -> tuple[int | None, int | None]:
        assert settings.api_key is not None
        platform = SdkSessionPlatform(settings.api_key)
        try:
            first = await run_session(
                platform,
                Path("fixtures/tiny.csv"),
                agent.resource.id,
                environment.resource.id,
                "live-followup",
                budget_cents=100,
                timeout_s=600,
            )
            assert first.status == "completed", first
            directory = tmp_path / "live-followup" / "tiny"
            await collect(platform, first.session_id, directory, "tiny.csv")
            followup, files = await ask_session(
                platform,
                first.session_id,
                "Break values down with one chart",
                timeout_s=600,
                output_root=tmp_path,
            )
            assert followup.status == "completed", followup
            assert any(path.name == "followup_1_report.md" for path in files)
            assert any(path.name.startswith("followup_1_chart_") for path in files)
            history = await platform.list_events(first.session_id)
            followup_message = max(
                index
                for index, event in enumerate(history)
                if event.get("type") == "user.message"
            )
            assert any(
                event.get("type") == "agent.tool_use"
                and "/mnt/session/outputs/analysis.py" in json.dumps(event.get("input"))
                and (
                    event.get("name") == "read"
                    or (
                        event.get("name") == "bash"
                        and "cat" in json.dumps(event.get("input"))
                    )
                )
                for event in history[followup_message + 1 :]
            )
            printed: list[str] = []
            await tail_session(
                platform,
                first.session_id,
                sink=lambda event: printed.append(event.raw_type),
            )
            assert "session.status_idle" in printed
            (tmp_path / "live-followup" / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "live-followup",
                        "sessions": [{"session_id": first.session_id}],
                    }
                ),
                encoding="utf-8",
            )
            outcomes = await cleanup_run(
                platform, "live-followup", output_root=tmp_path
            )
            assert outcomes[0].action == "archived"
            return first.list_cost_cents, followup.list_cost_cents
        finally:
            await platform.close()

    first_cost, cumulative_cost = asyncio.run(execute())
    print(f"followup list_cost_cents before={first_cost} after={cumulative_cost}")
