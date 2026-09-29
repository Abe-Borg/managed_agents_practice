"""One opt-in, budgeted end-to-end session against Claude Managed Agents."""

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
from csv_analyst.runner import run_session


@pytest.mark.live
def test_tiny_file_produces_report_chart_script_and_manifest(tmp_path: Path) -> None:
    if os.environ.get("CSV_ANALYST_LIVE") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE=1 to run the live smoke test")
    settings = load_settings()
    if settings.api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY available")

    setup_platform = SdkPlatform(settings.api_key)
    environment = ensure_environment(setup_platform, build_environment_spec())
    if load_state().agent_id is None:
        ensure_agent(setup_platform, build_agent_spec(settings))
    skill = ensure_skill(setup_platform, SKILL_DIR)
    agent = ensure_agent(
        setup_platform, build_agent_spec(settings, skill_id=skill.resource.id)
    )
    tiny = Path("fixtures/tiny.csv")

    async def execute() -> tuple[str, int | None]:
        assert settings.api_key is not None
        platform = SdkSessionPlatform(settings.api_key)
        try:
            result = await run_session(
                platform,
                tiny,
                agent.resource.id,
                environment.resource.id,
                "live-test",
                budget_cents=25,
                timeout_s=600,
            )
            assert result.status == "completed", result
            outputs = await collect(
                platform, result.session_id, tmp_path / "tiny", tiny.name
            )
            assert {"report.md", "analysis.py", "manifest.json"} <= {
                path.name for path in outputs.files
            }
            assert any(path.name.startswith("chart_") for path in outputs.files)
            assert json.loads((outputs.directory / "manifest.json").read_text())[
                "uploads_seen"
            ] == ["tiny.csv"]
            return result.session_id, result.list_cost_cents
        finally:
            await platform.close()

    session_id, cost = asyncio.run(execute())
    print(f"session={session_id} list_cost_cents={cost}")
