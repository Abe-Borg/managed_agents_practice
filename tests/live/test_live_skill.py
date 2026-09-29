"""Opt-in Phase 4 check: three sessions, each capped at 50 cents."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from csv_analyst.cli import app
from csv_analyst.config import load_settings
from csv_analyst.resources import load_state


def _run_tiny(*options: str) -> tuple[str, Path]:
    before = set(Path("runs").glob("*/tiny"))
    result = CliRunner().invoke(
        app, ["run", "fixtures/tiny.csv", "--budget-cents", "50", *options]
    )
    assert result.exit_code == 0, result.output
    created = set(Path("runs").glob("*/tiny")) - before
    assert len(created) == 1
    return result.output, created.pop()


@pytest.mark.live
def test_skill_version_pin_and_session_model_override() -> None:
    if os.environ.get("CSV_ANALYST_LIVE") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE=1 to run the live Skill check")
    if load_settings().api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY available")

    setup = CliRunner().invoke(app, ["setup"])
    assert setup.exit_code == 0, setup.output
    state = load_state()
    assert state.agent_version == 2
    assert state.skill_id is not None

    skilled_output, skilled_dir = _run_tiny()
    assert "Agent version: 2" in skilled_output
    assert state.skill_id in skilled_output
    report = (skilled_dir / "report.md").read_text(encoding="utf-8")
    for heading in (
        "## Overview",
        "## Data quality",
        "## Key findings",
        "## Charts",
        "## Caveats",
        "## Reproduce",
    ):
        assert heading in report
    skilled_manifest = json.loads(
        (skilled_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert skilled_manifest["skill_used"] is True

    pinned_output, pinned_dir = _run_tiny("--agent-version", "1")
    assert "Agent version: 1" in pinned_output
    assert "Attached Skills: none" in pinned_output
    pinned_manifest = json.loads(
        (pinned_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert pinned_manifest["skill_used"] is False

    override_output, override_dir = _run_tiny("--model", "claude-sonnet-5-5")
    assert "Agent version: 2" in override_output
    assert "Model: claude-sonnet-5-5" in override_output
    assert override_dir.joinpath("report.md").is_file()
    assert load_state().agent_version == 2
    print("Phase 4 sessions completed; each session had a 50-cent cap")
