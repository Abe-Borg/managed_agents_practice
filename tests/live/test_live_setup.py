"""Opt-in resource setup smoke test; never runs in offline CI."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from csv_analyst.cli import app
from csv_analyst.config import load_settings


@pytest.mark.live_extra
def test_setup_twice_reuses_saved_resources() -> None:
    if os.environ.get("CSV_ANALYST_LIVE_EXTRA") != "1":
        pytest.skip("Set CSV_ANALYST_LIVE_EXTRA=1 for additional live calls")
    if load_settings().api_key is None:
        pytest.skip("No ANTHROPIC_API_KEY is configured")

    runner = CliRunner()
    first = runner.invoke(app, ["setup"])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, ["setup"])
    assert second.exit_code == 0, second.output
    assert "unchanged" in second.output

    resources = runner.invoke(app, ["resources"])
    assert resources.exit_code == 0, resources.output
    assert "Agent versions" in resources.output
