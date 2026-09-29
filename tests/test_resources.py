from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

import csv_analyst.cli as cli_module
from csv_analyst.agent_spec import (
    EnvironmentSpec,
    build_agent_spec,
    build_environment_spec,
)
from csv_analyst.cli import app
from csv_analyst.config import load_settings
from csv_analyst.platform import EnvironmentInfo, PlatformValidationError
from csv_analyst.resources import (
    ensure_agent,
    ensure_environment,
    load_state,
    save_state,
)
from tests.fakes import FakePlatform


def test_agent_setup_is_idempotent_and_system_change_creates_version_2(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    state_path = tmp_path / "state.json"
    settings = load_settings(env={}, dotenv_path=None)
    first_spec = build_agent_spec(settings)

    first = ensure_agent(platform, first_spec, state_path)
    second = ensure_agent(platform, first_spec, state_path)
    changed = ensure_agent(
        platform,
        build_agent_spec(settings, system="Updated analyst instructions."),
        state_path,
    )

    assert (first.action, second.action, changed.action) == (
        "created",
        "unchanged",
        "updated",
    )
    assert first.resource.id == second.resource.id == changed.resource.id
    assert changed.resource.version == 2
    assert platform.agent_creates == 1
    assert platform.agent_updates == 1
    assert load_state(state_path).agent_version == 2


def test_agent_update_retries_once_after_stale_version(tmp_path: Path) -> None:
    platform = FakePlatform()
    state_path = tmp_path / "state.json"
    settings = load_settings(env={}, dotenv_path=None)
    original = ensure_agent(platform, build_agent_spec(settings), state_path)
    platform.agents[original.resource.id].version = 2
    platform.agents[original.resource.id].spec_hash = "external-change"

    result = ensure_agent(
        platform, build_agent_spec(settings, system="New instructions."), state_path
    )

    assert result.action == "updated"
    assert result.resource.version == 3
    assert platform.agent_conflicts == 1
    assert platform.agent_updates == 1


def test_environment_setup_is_idempotent_and_replaces_changed_config(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    state_path = tmp_path / "state.json"
    limited = build_environment_spec()

    first = ensure_environment(platform, limited, state_path)
    second = ensure_environment(platform, limited, state_path)
    unrestricted = replace(
        limited, config={"type": "cloud", "networking": {"type": "unrestricted"}}
    )
    changed = ensure_environment(platform, unrestricted, state_path)

    assert (first.action, second.action, changed.action) == (
        "created",
        "unchanged",
        "updated",
    )
    assert changed.resource.id != first.resource.id
    assert platform.environments[first.resource.id].archived
    assert platform.environment_creates == 2
    assert platform.environment_archives == 1
    assert load_state(state_path).environment_id == changed.resource.id
    assert load_state(state_path).pending_archive_environment_id is None


def test_environment_archive_failure_is_retried_without_creating_another(
    tmp_path: Path,
) -> None:
    class FailsArchiveOnce(FakePlatform):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_archive = True

        def archive_environment(self, environment_id: str) -> EnvironmentInfo:
            if self.fail_next_archive:
                self.fail_next_archive = False
                raise RuntimeError("temporary archive failure")
            return super().archive_environment(environment_id)

    platform = FailsArchiveOnce()
    state_path = tmp_path / "state.json"
    original = ensure_environment(platform, build_environment_spec(), state_path)
    changed_spec = replace(
        build_environment_spec(),
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )

    with pytest.raises(RuntimeError, match="temporary archive failure"):
        ensure_environment(platform, changed_spec, state_path)

    interrupted_state = load_state(state_path)
    assert interrupted_state.pending_archive_environment_id == original.resource.id
    assert interrupted_state.environment_id != original.resource.id
    assert not platform.environments[original.resource.id].archived

    retried = ensure_environment(platform, changed_spec, state_path)

    assert retried.action == "unchanged"
    assert retried.resource.id == interrupted_state.environment_id
    assert platform.environments[original.resource.id].archived
    assert platform.environment_creates == 2
    assert platform.environment_archives == 1
    assert load_state(state_path).pending_archive_environment_id is None


def test_state_write_is_complete_and_invalid_json_is_rejected(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "state.json"
    original = load_state(state_path)
    save_state(replace(original, agent_id="agent_1", agent_version=1), state_path)
    assert load_state(state_path).agent_id == "agent_1"
    assert list(state_path.parent.iterdir()) == [state_path]

    state_path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read resource state"):
        load_state(state_path)


def test_rejected_empty_host_list_uses_and_remembers_fallback(tmp_path: Path) -> None:
    class RejectEmptyHosts(FakePlatform):
        def __init__(self) -> None:
            super().__init__()
            self.rejections = 0

        def create_environment(self, spec: EnvironmentSpec) -> EnvironmentInfo:
            if spec.config == build_environment_spec().config:
                self.rejections += 1
                raise PlatformValidationError("empty hosts rejected")
            return super().create_environment(spec)

    platform = RejectEmptyHosts()
    state_path = tmp_path / "state.json"

    first = ensure_environment(platform, build_environment_spec(), state_path)
    second = ensure_environment(platform, build_environment_spec(), state_path)

    assert first.detail == second.detail == "unrestricted-fallback"
    assert (first.action, second.action) == ("created", "unchanged")
    assert platform.rejections == 1
    assert platform.environment_creates == 1
    assert load_state(state_path).environment_mode == "unrestricted-fallback"


def test_setup_and_resources_commands_use_saved_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    platform = FakePlatform()
    monkeypatch.chdir(tmp_path)
    source_skill = Path(__file__).resolve().parents[1] / "skills" / "csv-report"
    shutil.copytree(source_skill, tmp_path / "skills" / "csv-report")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-cli-test")
    monkeypatch.setattr(cli_module, "SdkPlatform", lambda _key: platform)
    runner = CliRunner()

    first = runner.invoke(app, ["setup"])
    second = runner.invoke(app, ["setup"])
    listed = runner.invoke(app, ["resources"])

    assert first.exit_code == second.exit_code == listed.exit_code == 0
    assert "Skill: skill_1" in first.output
    assert "updated" in first.output and "v2" in first.output
    assert "unchanged" in second.output
    assert platform.agent_creates == 1
    assert platform.agent_updates == 1
    assert "Agent versions" in listed.output
    assert "Skill: skill_1" in listed.output
    assert "agent_1" in listed.output


@pytest.mark.parametrize("stale_mode", ["archived", "deleted"])
def test_setup_bootstraps_unskilled_agent_after_stale_saved_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stale_mode: str
) -> None:
    platform = FakePlatform()
    monkeypatch.chdir(tmp_path)
    source_skill = Path(__file__).resolve().parents[1] / "skills" / "csv-report"
    shutil.copytree(source_skill, tmp_path / "skills" / "csv-report")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-cli-test")
    monkeypatch.setattr(cli_module, "SdkPlatform", lambda _key: platform)
    runner = CliRunner()

    first = runner.invoke(app, ["setup"])
    assert first.exit_code == 0, first.output
    if stale_mode == "archived":
        platform.agents["agent_1"].archived = True
    else:
        del platform.agents["agent_1"]

    second = runner.invoke(app, ["setup"])

    assert second.exit_code == 0, second.output
    assert "Agent: agent_2 v2" in second.output
    assert platform.agent_creates == 2
    assert platform.agent_updates == 2
    assert load_state().agent_id == "agent_2"
    assert load_state().agent_version == 2
