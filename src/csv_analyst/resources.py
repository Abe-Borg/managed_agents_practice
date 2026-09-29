"""Idempotent setup of saved Agent and Environment resources."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from csv_analyst.agent_spec import AgentSpec, EnvironmentSpec, config_hash
from csv_analyst.platform import (
    AgentInfo,
    EnvironmentInfo,
    Platform,
    PlatformConflict,
    PlatformNotFound,
    PlatformValidationError,
)

STATE_PATH = Path(".csv-analyst/state.json")
Action = Literal["created", "updated", "unchanged"]


@dataclass(frozen=True)
class ResourceState:
    environment_id: str | None = None
    environment_hash: str | None = None
    environment_mode: str | None = None
    pending_archive_environment_id: str | None = None
    agent_id: str | None = None
    agent_version: int | None = None
    config_hash: str | None = None
    skill_id: str | None = None
    skill_version: str | None = None


@dataclass(frozen=True)
class ResourceResult[T]:
    resource: T
    action: Action
    detail: str | None = None


def load_state(path: Path = STATE_PATH) -> ResourceState:
    if not path.exists():
        return ResourceState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read resource state at {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Resource state at {path} must be a JSON object")
    try:
        state = ResourceState(**data)
    except TypeError as exc:
        raise ValueError(f"Resource state at {path} has unexpected fields") from exc
    if state.agent_version is not None and (
        not isinstance(state.agent_version, int) or state.agent_version < 1
    ):
        raise ValueError(f"Resource state at {path} has an invalid agent version")
    for field_name in (
        "environment_id",
        "environment_hash",
        "environment_mode",
        "pending_archive_environment_id",
        "agent_id",
        "config_hash",
        "skill_id",
        "skill_version",
    ):
        value = getattr(state, field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Resource state at {path} has an invalid {field_name}")
    return state


def save_state(state: ResourceState, path: Path = STATE_PATH) -> None:
    """Replace state atomically; a failed write leaves the previous file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(asdict(state), stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def ensure_environment(
    platform: Platform,
    spec: EnvironmentSpec,
    state_path: Path = STATE_PATH,
) -> ResourceResult[EnvironmentInfo]:
    state = load_state(state_path)
    if state.pending_archive_environment_id:
        try:
            pending = platform.retrieve_environment(
                state.pending_archive_environment_id
            )
        except PlatformNotFound:
            pending = None
        if pending is not None and not pending.archived:
            platform.archive_environment(pending.id)
        state = replace(state, pending_archive_environment_id=None)
        save_state(state, state_path)

    desired_hash = config_hash(spec.hash_input())
    previous: EnvironmentInfo | None = None
    if state.environment_id:
        try:
            previous = platform.retrieve_environment(state.environment_id)
        except PlatformNotFound:
            previous = None
        if (
            previous is not None
            and not previous.archived
            and state.environment_hash == desired_hash
        ):
            return ResourceResult(previous, "unchanged", state.environment_mode)

    mode = "limited"
    try:
        created = platform.create_environment(spec)
    except PlatformValidationError:
        networking = spec.config.get("networking")
        if not (
            isinstance(networking, dict)
            and networking.get("type") == "limited"
            and networking.get("allowed_hosts") == []
        ):
            raise
        fallback = EnvironmentSpec(
            name=spec.name,
            config={"type": "cloud", "networking": {"type": "unrestricted"}},
        )
        created = platform.create_environment(fallback)
        mode = "unrestricted-fallback"
    new_state = replace(
        state,
        environment_id=created.id,
        environment_hash=desired_hash,
        environment_mode=mode,
        pending_archive_environment_id=(
            previous.id if previous is not None and not previous.archived else None
        ),
    )
    save_state(new_state, state_path)
    if previous is not None and not previous.archived:
        platform.archive_environment(previous.id)
        save_state(replace(new_state, pending_archive_environment_id=None), state_path)
        return ResourceResult(created, "updated", mode)
    return ResourceResult(created, "created", mode)


def ensure_agent(
    platform: Platform,
    spec: AgentSpec,
    state_path: Path = STATE_PATH,
) -> ResourceResult[AgentInfo]:
    state = load_state(state_path)
    desired_hash = config_hash(spec.hash_input())
    previous: AgentInfo | None = None
    if state.agent_id:
        try:
            previous = platform.retrieve_agent(state.agent_id)
        except PlatformNotFound:
            previous = None
        if (
            previous is not None
            and not previous.archived
            and state.config_hash == desired_hash
            and state.agent_version == previous.version
        ):
            return ResourceResult(previous, "unchanged")

    if previous is None or previous.archived:
        created = platform.create_agent(spec)
        save_state(
            replace(
                state,
                agent_id=created.id,
                agent_version=created.version,
                config_hash=desired_hash,
            ),
            state_path,
        )
        return ResourceResult(created, "created")

    expected_version = state.agent_version or previous.version
    try:
        updated = platform.update_agent(previous.id, expected_version, spec)
    except PlatformConflict:
        current = platform.retrieve_agent(previous.id)
        if current.archived:
            created = platform.create_agent(spec)
            save_state(
                replace(
                    state,
                    agent_id=created.id,
                    agent_version=created.version,
                    config_hash=desired_hash,
                ),
                state_path,
            )
            return ResourceResult(created, "created")
        updated = platform.update_agent(current.id, current.version, spec)

    save_state(
        replace(state, agent_version=updated.version, config_hash=desired_hash),
        state_path,
    )
    action: Action = "updated" if updated.version > previous.version else "unchanged"
    return ResourceResult(updated, action)
