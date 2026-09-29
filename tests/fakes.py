"""In-memory Phase 2 platform with the same resource rules used by the app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from csv_analyst.agent_spec import AgentSpec, EnvironmentSpec, config_hash
from csv_analyst.platform import (
    AgentInfo,
    AgentVersionInfo,
    EnvironmentInfo,
    OutputFileInfo,
    PlatformConflict,
    PlatformNotFound,
    SessionInfo,
    SkillInfo,
)


@dataclass
class _AgentRecord:
    spec_hash: str
    version: int = 1
    archived: bool = False


@dataclass
class _EnvironmentRecord:
    spec_hash: str
    archived: bool = False


class FakePlatform:
    def __init__(self) -> None:
        self.agents: dict[str, _AgentRecord] = {}
        self.environments: dict[str, _EnvironmentRecord] = {}
        self.agent_creates = 0
        self.agent_updates = 0
        self.environment_creates = 0
        self.environment_archives = 0
        self.agent_conflicts = 0
        self.skills: dict[str, str] = {}
        self.skill_creates = 0
        self.skill_version_creates = 0

    def create_environment(self, spec: EnvironmentSpec) -> EnvironmentInfo:
        self.environment_creates += 1
        identifier = f"env_{self.environment_creates}"
        self.environments[identifier] = _EnvironmentRecord(
            spec_hash=config_hash(spec.hash_input())
        )
        return EnvironmentInfo(identifier, False)

    def retrieve_environment(self, environment_id: str) -> EnvironmentInfo:
        record = self.environments.get(environment_id)
        if record is None:
            raise PlatformNotFound(environment_id)
        return EnvironmentInfo(environment_id, record.archived)

    def archive_environment(self, environment_id: str) -> EnvironmentInfo:
        record = self.environments.get(environment_id)
        if record is None:
            raise PlatformNotFound(environment_id)
        record.archived = True
        self.environment_archives += 1
        return EnvironmentInfo(environment_id, True)

    def create_agent(self, spec: AgentSpec) -> AgentInfo:
        self.agent_creates += 1
        identifier = f"agent_{self.agent_creates}"
        self.agents[identifier] = _AgentRecord(spec_hash=config_hash(spec.hash_input()))
        return self.retrieve_agent(identifier)

    def retrieve_agent(self, agent_id: str) -> AgentInfo:
        record = self.agents.get(agent_id)
        if record is None:
            raise PlatformNotFound(agent_id)
        return AgentInfo(
            id=agent_id,
            version=record.version,
            archived=record.archived,
            updated_at=f"2026-09-28T00:00:0{record.version}Z",
        )

    def update_agent(self, agent_id: str, version: int, spec: AgentSpec) -> AgentInfo:
        record = self.agents.get(agent_id)
        if record is None:
            raise PlatformNotFound(agent_id)
        if version != record.version:
            self.agent_conflicts += 1
            raise PlatformConflict(agent_id)
        new_hash = config_hash(spec.hash_input())
        if new_hash != record.spec_hash:
            record.spec_hash = new_hash
            record.version += 1
            self.agent_updates += 1
        return self.retrieve_agent(agent_id)

    def list_agent_versions(self, agent_id: str) -> list[AgentVersionInfo]:
        record = self.agents.get(agent_id)
        if record is None:
            raise PlatformNotFound(agent_id)
        return [
            AgentVersionInfo(version, f"2026-09-28T00:00:0{version}Z")
            for version in range(1, record.version + 1)
        ]

    def create_skill(self, directory: Path) -> SkillInfo:
        self.skill_creates += 1
        skill_id = f"skill_{self.skill_creates}"
        version_id = f"skver_{self.skill_creates}_1"
        self.skills[skill_id] = version_id
        return SkillInfo(skill_id, version_id)

    def retrieve_skill(self, skill_id: str) -> SkillInfo:
        version_id = self.skills.get(skill_id)
        if version_id is None:
            raise PlatformNotFound(skill_id)
        return SkillInfo(skill_id, version_id)

    def create_skill_version(self, skill_id: str, directory: Path) -> SkillInfo:
        if skill_id not in self.skills:
            raise PlatformNotFound(skill_id)
        self.skill_version_creates += 1
        version_id = f"skver_{skill_id}_{self.skill_version_creates + 1}"
        self.skills[skill_id] = version_id
        return SkillInfo(skill_id, version_id)


class FakeEventStream:
    def __init__(self, events: list[dict[str, Any]], calls: list[str]) -> None:
        self.events = events
        self.calls = calls

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def close(self) -> None:
        self.calls.append("stream.close")


class FakeSessionPlatform:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events = events or []
        self.history_events: list[dict[str, Any]] | None = None
        self.calls: list[str] = []
        self.budget_cents: int | None = None
        self.output_schedule: list[list[OutputFileInfo]] = []
        self.output_payloads: dict[str, bytes] = {}
        self.list_calls = 0
        self.agent_reference: str | dict[str, Any] | None = None
        self.saved_agent_version = 2
        self.saved_model = "claude-haiku-4-5"
        self.saved_skill_ids = ("skill_1",)
        self.session_status = "idle"
        self.session_cost = 6
        self.session_budget = 5
        self.updated_budget: int | None = None

    async def close(self) -> None:
        self.calls.append("platform.close")

    async def upload_file(self, path: Path) -> str:
        self.calls.append("upload")
        return "file_input"

    async def create_session(
        self,
        agent_id: str,
        environment_id: str,
        file_id: str,
        input_name: str,
        budget_cents: int | None,
        run_id: str,
        *,
        agent_version: int | None = None,
        model: str | None = None,
    ) -> SessionInfo:
        self.calls.append("session.create")
        self.budget_cents = budget_cents
        if model is not None:
            self.agent_reference = {
                "type": "agent_with_overrides",
                "id": agent_id,
                "model": {"id": model},
            }
            if agent_version is not None:
                self.agent_reference["version"] = agent_version
        elif agent_version is not None:
            self.agent_reference = {
                "type": "agent",
                "id": agent_id,
                "version": agent_version,
            }
        else:
            self.agent_reference = agent_id
        resolved_version = agent_version or self.saved_agent_version
        return SessionInfo(
            "sesn_fake",
            "pending",
            agent_version=resolved_version,
            model=model or self.saved_model,
            skill_ids=() if resolved_version == 1 else self.saved_skill_ids,
        )

    async def open_event_stream(self, session_id: str) -> FakeEventStream:
        self.calls.append("stream.open")
        return FakeEventStream(self.events, self.calls)

    async def send_message(self, session_id: str, message: str) -> None:
        self.calls.append("events.send_message")

    async def send_interrupt(self, session_id: str) -> None:
        self.calls.append("events.send_interrupt")

    async def retrieve_session(self, session_id: str) -> SessionInfo:
        return SessionInfo(
            session_id,
            self.session_status,
            title="csv-analyst: tiny.csv",
            budget_cents=self.session_budget,
            list_cost_cents=self.session_cost,
            active_seconds=1.0,
        )

    async def update_session_budget(self, session_id: str, to_cents: int) -> None:
        self.calls.append("session.update_budget")
        self.updated_budget = to_cents

    async def archive_session(self, session_id: str) -> SessionInfo:
        return SessionInfo(session_id, "archived")

    async def list_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.history_events if self.history_events is not None else self.events

    async def list_output_files(self, session_id: str) -> list[OutputFileInfo]:
        self.list_calls += 1
        if not self.output_schedule:
            return []
        index = min(self.list_calls - 1, len(self.output_schedule) - 1)
        return self.output_schedule[index]

    async def download_file(self, file_id: str, dest: Path) -> None:
        self.calls.append(f"file.download:{file_id}")
        dest.write_bytes(self.output_payloads[file_id])
