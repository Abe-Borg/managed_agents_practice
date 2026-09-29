"""One opt-in Phase 2–6 acceptance pass, capped at four sessions total."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from csv_analyst.agent_spec import build_agent_spec, build_environment_spec
from csv_analyst.config import load_settings
from csv_analyst.orchestrator import check_isolation
from csv_analyst.outputs import collect
from csv_analyst.platform import PlatformNotFound, SdkPlatform, SdkSessionPlatform
from csv_analyst.resources import (
    SKILL_DIR,
    ensure_agent,
    ensure_environment,
    ensure_skill,
    load_state,
)
from csv_analyst.runner import (
    ask_session,
    cleanup_run,
    resume_budget_session,
    run_session,
    tail_session,
)


@pytest.mark.live
def test_four_session_acceptance(tmp_path: Path) -> None:
    if os.environ.get("CSV_ANALYST_LIVE") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE=1 to enable the four-session live pass")
    settings = load_settings()
    if settings.api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY configured locally")

    setup = SdkPlatform(settings.api_key)
    environment = ensure_environment(setup, build_environment_spec())
    saved_agent_id = load_state().agent_id
    try:
        saved_agent = (
            setup.retrieve_agent(saved_agent_id) if saved_agent_id is not None else None
        )
    except PlatformNotFound:
        saved_agent = None
    if saved_agent is None or saved_agent.archived:
        ensure_agent(setup, build_agent_spec(settings))
    skill = ensure_skill(setup, SKILL_DIR)
    agent = ensure_agent(setup, build_agent_spec(settings, skill_id=skill.resource.id))
    assert agent.resource.version >= 2
    assert ensure_environment(setup, build_environment_spec()).action == "unchanged"
    assert ensure_skill(setup, SKILL_DIR).action == "unchanged"
    assert (
        ensure_agent(
            setup, build_agent_spec(settings, skill_id=skill.resource.id)
        ).action
        == "unchanged"
    )
    assert setup.list_agent_versions(agent.resource.id)

    async def execute() -> None:
        assert settings.api_key is not None
        names = ("sales", "weather", "web_traffic")
        versions = (None, 1, None)
        models = (None, None, "claude-sonnet-5-5")

        async def one(index: int):
            platform = SdkSessionPlatform(settings.api_key)
            name = names[index]
            started = datetime.now(UTC)
            try:
                result = await run_session(
                    platform,
                    Path("fixtures") / f"{name}.csv",
                    agent.resource.id,
                    environment.resource.id,
                    "live-acceptance",
                    budget_cents=100,
                    timeout_s=600,
                    agent_version=versions[index],
                    model=models[index],
                )
                assert result.status == "completed", result
                outputs = await collect(
                    platform,
                    result.session_id,
                    tmp_path / "live-acceptance" / name,
                    f"{name}.csv",
                )
                assert check_isolation(outputs.manifest, f"{name}.csv")
                assert result.list_cost_cents is not None
                return started, datetime.now(UTC), result, outputs
            finally:
                await platform.close()

        parallel = await asyncio.gather(*(one(i) for i in range(3)))
        assert max(row[0] for row in parallel) < min(row[1] for row in parallel)
        assert len({row[2].session_id for row in parallel}) == 3
        sales, weather, traffic = parallel
        assert skill.resource.id in sales[2].skill_ids
        assert sales[3].manifest["skill_used"] is True
        assert weather[2].agent_version == 1
        assert weather[2].skill_ids == ()
        assert weather[3].manifest["skill_used"] is False
        assert traffic[2].model == "claude-sonnet-5-5"
        for heading in (
            "## Overview",
            "## Data quality",
            "## Key findings",
            "## Charts",
            "## Caveats",
            "## Reproduce",
        ):
            assert heading in (sales[3].directory / "report.md").read_text(
                encoding="utf-8"
            )

        platform = SdkSessionPlatform(settings.api_key)
        try:
            followup, files = await ask_session(
                platform,
                sales[2].session_id,
                "Break revenue down by region with one chart",
                timeout_s=600,
                output_root=tmp_path,
            )
            assert followup.status == "completed", followup
            assert any(path.name == "followup_1_report.md" for path in files)
            assert any(path.name.startswith("followup_1_chart_") for path in files)
            history = await platform.list_events(sales[2].session_id)
            last_message = max(
                i
                for i, event in enumerate(history)
                if event.get("type") == "user.message"
            )
            assert any(
                event.get("type") == "agent.tool_use"
                and "/mnt/session/outputs/analysis.py" in json.dumps(event.get("input"))
                for event in history[last_message + 1 :]
            )
            replayed: list[str] = []
            await tail_session(
                platform,
                sales[2].session_id,
                sink=lambda event: replayed.append(event.raw_type),
            )
            assert "session.status_idle" in replayed

            run_dir = tmp_path / "live-acceptance"
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "live-acceptance",
                        "sessions": [
                            {"session_id": row[2].session_id} for row in parallel
                        ],
                    }
                ),
                encoding="utf-8",
            )
            archived = await cleanup_run(
                platform, "live-acceptance", output_root=tmp_path
            )
            assert all(item.action == "archived" for item in archived)

            paused = await run_session(
                platform,
                Path("fixtures/sales.csv"),
                agent.resource.id,
                environment.resource.id,
                "live-budget",
                budget_cents=5,
                timeout_s=600,
            )
            assert paused.status == "paused_budget", paused
            resumed = await resume_budget_session(
                platform, paused.session_id, 100, timeout_s=600
            )
            assert resumed.status == "completed", resumed
            await collect(
                platform,
                paused.session_id,
                tmp_path / "live-budget" / "sales",
                "sales.csv",
            )
            await platform.archive_session(paused.session_id)
            print(
                "parallel list_cost_cents="
                f"{[row[2].list_cost_cents for row in parallel]} "
                "active_seconds="
                f"{[row[2].active_seconds for row in parallel]}"
            )
            print(
                f"followup cumulative_list_cost_cents={followup.list_cost_cents} "
                f"active_seconds={followup.active_seconds}"
            )
            print(
                f"budget before_cents={paused.list_cost_cents} "
                f"after_cents={resumed.list_cost_cents} "
                f"active_seconds={resumed.active_seconds}"
            )
        finally:
            await platform.close()

    asyncio.run(execute())
