from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import csv_analyst.cli as cli_module
from csv_analyst.cli import app
from csv_analyst.platform import OutputFileInfo
from csv_analyst.resources import ResourceState, save_state
from tests.fakes import FakeSessionPlatform


def test_run_command_downloads_artifacts_with_fake_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-cli-test")
    Path("tiny.csv").write_text("x\n1\n", encoding="utf-8")
    save_state(ResourceState(agent_id="agent_1", environment_id="env_1"))
    fixture = Path(__file__).parent / "fixtures" / "events" / "tiny_end_turn.jsonl"
    events = [json.loads(line) for line in fixture.read_text().splitlines()]
    platform = FakeSessionPlatform(events)
    names = ["report.md", "analysis.py", "chart_01_values.png", "manifest.json"]
    platform.output_schedule = [[OutputFileInfo(name, name) for name in names]]
    platform.output_payloads = {
        "report.md": b"# Tiny report",
        "analysis.py": b"print('tiny')",
        "chart_01_values.png": b"\x89PNG\r\n\x1a\n",
        "manifest.json": json.dumps(
            {
                "input_file": "tiny.csv",
                "uploads_seen": ["tiny.csv"],
                "markers_seen_before_write": [],
                "rows": 1,
                "columns": 1,
                "charts": ["chart_01_values.png"],
                "summary": "Tiny data",
            }
        ).encode(),
    }
    monkeypatch.setattr(cli_module, "SdkSessionPlatform", lambda _key: platform)

    result = CliRunner().invoke(app, ["run", "tiny.csv", "--budget-cents", "50"])

    assert result.exit_code == 0, result.output
    assert "Session: sesn_fake" in result.output
    assert "Artifacts:" in result.output
    assert platform.budget_cents == 50
    assert len(list(Path("runs").glob("*/tiny/report.md"))) == 1
