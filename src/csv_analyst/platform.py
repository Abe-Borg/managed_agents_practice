"""Small boundary around the Managed Agents calls used in Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from anthropic import Anthropic, BadRequestError, ConflictError, NotFoundError

from csv_analyst.agent_spec import AgentSpec, EnvironmentSpec


class PlatformNotFound(Exception):
    """A saved resource no longer exists."""


class PlatformConflict(Exception):
    """The Agent version changed during an update."""


class PlatformValidationError(Exception):
    """The API rejected a resource specification."""


@dataclass(frozen=True)
class AgentInfo:
    id: str
    version: int
    archived: bool
    updated_at: str


@dataclass(frozen=True)
class AgentVersionInfo:
    version: int
    updated_at: str


@dataclass(frozen=True)
class EnvironmentInfo:
    id: str
    archived: bool


class Platform(Protocol):
    def create_environment(self, spec: EnvironmentSpec) -> EnvironmentInfo: ...

    def retrieve_environment(self, environment_id: str) -> EnvironmentInfo: ...

    def archive_environment(self, environment_id: str) -> EnvironmentInfo: ...

    def create_agent(self, spec: AgentSpec) -> AgentInfo: ...

    def retrieve_agent(self, agent_id: str) -> AgentInfo: ...

    def update_agent(
        self, agent_id: str, version: int, spec: AgentSpec
    ) -> AgentInfo: ...

    def list_agent_versions(self, agent_id: str) -> list[AgentVersionInfo]: ...


class SdkPlatform:
    """Only this module calls the Anthropic SDK."""

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    def create_environment(self, spec: EnvironmentSpec) -> EnvironmentInfo:
        try:
            resource = self._client.beta.environments.create(
                name=spec.name,
                config=cast(Any, spec.config),
            )
        except BadRequestError as exc:
            raise PlatformValidationError("Environment configuration rejected") from exc
        return EnvironmentInfo(
            id=resource.id,
            archived=resource.archived_at is not None,
        )

    def retrieve_environment(self, environment_id: str) -> EnvironmentInfo:
        try:
            resource = self._client.beta.environments.retrieve(environment_id)
        except NotFoundError as exc:
            raise PlatformNotFound(environment_id) from exc
        return EnvironmentInfo(
            id=resource.id,
            archived=resource.archived_at is not None,
        )

    def archive_environment(self, environment_id: str) -> EnvironmentInfo:
        resource = self._client.beta.environments.archive(environment_id)
        return EnvironmentInfo(
            id=resource.id,
            archived=resource.archived_at is not None,
        )

    def create_agent(self, spec: AgentSpec) -> AgentInfo:
        resource = self._client.beta.agents.create(
            name=spec.name,
            model=spec.model,
            system=spec.system,
            tools=cast(Any, spec.tools),
            skills=cast(Any, spec.skills),
            metadata=spec.metadata,
        )
        return AgentInfo(
            id=resource.id,
            version=resource.version,
            archived=resource.archived_at is not None,
            updated_at=resource.updated_at.isoformat(),
        )

    def retrieve_agent(self, agent_id: str) -> AgentInfo:
        try:
            resource = self._client.beta.agents.retrieve(agent_id)
        except NotFoundError as exc:
            raise PlatformNotFound(agent_id) from exc
        return AgentInfo(
            id=resource.id,
            version=resource.version,
            archived=resource.archived_at is not None,
            updated_at=resource.updated_at.isoformat(),
        )

    def update_agent(self, agent_id: str, version: int, spec: AgentSpec) -> AgentInfo:
        try:
            resource = self._client.beta.agents.update(
                agent_id,
                version=version,
                name=spec.name,
                model=spec.model,
                system=spec.system,
                tools=cast(Any, spec.tools),
                skills=cast(Any, spec.skills),
                metadata=cast(dict[str, str | None], spec.metadata),
            )
        except ConflictError as exc:
            raise PlatformConflict(agent_id) from exc
        return AgentInfo(
            id=resource.id,
            version=resource.version,
            archived=resource.archived_at is not None,
            updated_at=resource.updated_at.isoformat(),
        )

    def list_agent_versions(self, agent_id: str) -> list[AgentVersionInfo]:
        versions = self._client.beta.agents.versions.list(agent_id)
        return [
            AgentVersionInfo(
                version=resource.version,
                updated_at=resource.updated_at.isoformat(),
            )
            for resource in versions
        ]
