from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from csv_analyst.cli import app
from csv_analyst.config import load_settings


@pytest.mark.parametrize("bad_budget", ["0", "1.50", "-1", "abc", ""])
def test_budget_must_be_positive_whole_cents(bad_budget: str) -> None:
    with pytest.raises(ValueError, match="CSV_ANALYST_BUDGET_CENTS"):
        load_settings(env={"CSV_ANALYST_BUDGET_CENTS": bad_budget}, dotenv_path=None)


def test_model_cannot_be_empty() -> None:
    with pytest.raises(ValueError, match="CSV_ANALYST_MODEL"):
        load_settings(env={"CSV_ANALYST_MODEL": "  "}, dotenv_path=None)


def test_dotenv_is_overridden_by_environment(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "CSV_ANALYST_MODEL=from-dotenv\nCSV_ANALYST_BUDGET_CENTS=75\n",
        encoding="utf-8",
    )
    settings = load_settings(
        env={"CSV_ANALYST_MODEL": "from-environment"}, dotenv_path=dotenv_path
    )
    assert settings.model == "from-environment"
    assert settings.budget_cents == 75


def test_key_is_redacted_from_repr_and_doctor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_key = "fake-secret-value-for-test"
    settings = load_settings(env={"ANTHROPIC_API_KEY": fake_key}, dotenv_path=None)
    assert fake_key not in repr(settings)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ANTHROPIC_API_KEY set: yes" in result.output
    assert fake_key not in result.output


def test_example_key_is_not_treated_as_configured() -> None:
    settings = load_settings(
        env={"ANTHROPIC_API_KEY": "sk-ant-REPLACE_ME"}, dotenv_path=None
    )
    assert settings.api_key is None


def test_dotenv_does_not_interpolate_key_into_displayed_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_key = "fake-secret-value-for-interpolation-test"
    (tmp_path / ".env").write_text(
        "CSV_ANALYST_MODEL=${ANTHROPIC_API_KEY}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert fake_key not in result.output


def test_model_that_contains_key_is_redacted_in_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_key = "fake-secret-value-for-model-test"
    settings = load_settings(
        env={"ANTHROPIC_API_KEY": fake_key, "CSV_ANALYST_MODEL": fake_key},
        dotenv_path=None,
    )
    assert fake_key not in repr(settings)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)
    monkeypatch.setenv("CSV_ANALYST_MODEL", fake_key)
    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert fake_key not in result.output
    assert "<redacted>" in result.output
