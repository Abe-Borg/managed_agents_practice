from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import csv_analyst.cli as cli_module
from csv_analyst.cli import app
from csv_analyst.resources import ResourceState, save_state
from tests.fakes import FakeSessionPlatform


def test_sessions_lists_recent_saved_agent_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-cli-test")
    save_state(ResourceState(agent_id="agent_1"))
    platform = FakeSessionPlatform()
    monkeypatch.setattr(cli_module, "SdkSessionPlatform", lambda _key: platform)
    result = CliRunner().invoke(app, ["sessions", "--limit", "5"])
    assert result.exit_code == 0, result.output
    assert "sesn_fake" in result.output
    assert "csv-analyst: tiny.csv" in result.output
    assert platform.calls == ["session.list", "platform.close"]
