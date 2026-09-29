"""In-memory Phase 2 platform with the same resource rules used by the app."""

from __future__ import annotations

from dataclasses import dataclass

from csv_analyst.agent_spec import AgentSpec, EnvironmentSpec, config_hash
from csv_analyst.platform import (
    AgentInfo,
    AgentVersionInfo,
    EnvironmentInfo,
    PlatformConflict,
    PlatformNotFound,
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
