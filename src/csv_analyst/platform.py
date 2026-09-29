"""Small boundary around the Managed Agents SDK calls."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from anthropic import (
    Anthropic,
    AsyncAnthropic,
    AsyncStream,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from anthropic.types.beta.sessions import BetaManagedAgentsStreamSessionEvents

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


@dataclass(frozen=True)
class SessionInfo:
    id: str
    status: str


@dataclass(frozen=True)
class OutputFileInfo:
    id: str
    filename: str


class SessionEventStream(Protocol):
    def __aiter__(self) -> AsyncIterator[dict[str, Any]]: ...

    async def close(self) -> None: ...


class SessionPlatform(Protocol):
    async def upload_file(self, path: Path) -> str: ...

    async def create_session(
        self,
        agent_id: str,
        environment_id: str,
        file_id: str,
        input_name: str,
        budget_cents: int | None,
        run_id: str,
    ) -> SessionInfo: ...

    async def open_event_stream(self, session_id: str) -> SessionEventStream: ...

    async def send_message(self, session_id: str, message: str) -> None: ...

    async def send_interrupt(self, session_id: str) -> None: ...

    async def retrieve_session(self, session_id: str) -> SessionInfo: ...

    async def archive_session(self, session_id: str) -> SessionInfo: ...

    async def list_events(self, session_id: str) -> list[dict[str, Any]]: ...

    async def list_output_files(self, session_id: str) -> list[OutputFileInfo]: ...

    async def download_file(self, file_id: str, dest: Path) -> None: ...


class _SdkEventStream:
    def __init__(
        self, stream: AsyncStream[BetaManagedAgentsStreamSessionEvents]
    ) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async for event in self._stream:
            yield event.model_dump(mode="json")

    async def close(self) -> None:
        await self._stream.close()


class SdkSessionPlatform:
    """Async file, session, and event methods used by the runner."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def close(self) -> None:
        await self._client.close()

    async def upload_file(self, path: Path) -> str:
        uploaded = await self._client.files.upload(file=path)
        return uploaded.id

    async def create_session(
        self,
        agent_id: str,
        environment_id: str,
        file_id: str,
        input_name: str,
        budget_cents: int | None,
        run_id: str,
    ) -> SessionInfo:
        fields: dict[str, Any] = {
            "agent": agent_id,
            "environment_id": environment_id,
            "resources": [
                {"type": "file", "file_id": file_id, "mount_path": f"/{input_name}"}
            ],
            "title": f"csv-analyst: {input_name}",
            "metadata": {"app": "csv-analyst", "run_id": run_id},
        }
        if budget_cents is not None:
            fields["budget"] = {
                "type": "limit",
                "max_list_cost": {"amount": str(budget_cents), "currency": "USD"},
            }
        session = await self._client.beta.sessions.create(**fields)
        return SessionInfo(session.id, session.status)

    async def open_event_stream(self, session_id: str) -> SessionEventStream:
        stream = await self._client.beta.sessions.events.stream(session_id)
        return _SdkEventStream(stream)

    async def send_message(self, session_id: str, message: str) -> None:
        await self._client.beta.sessions.events.send(
            session_id,
            events=[
                {"type": "user.message", "content": [{"type": "text", "text": message}]}
            ],
        )

    async def send_interrupt(self, session_id: str) -> None:
        await self._client.beta.sessions.events.send(
            session_id, events=[{"type": "user.interrupt"}]
        )

    async def retrieve_session(self, session_id: str) -> SessionInfo:
        session = await self._client.beta.sessions.retrieve(session_id)
        return SessionInfo(session.id, session.status)

    async def archive_session(self, session_id: str) -> SessionInfo:
        session = await self._client.beta.sessions.archive(session_id)
        return SessionInfo(session.id, session.status)

    async def list_events(self, session_id: str) -> list[dict[str, Any]]:
        return [
            event.model_dump(mode="json")
            async for event in self._client.beta.sessions.events.list(session_id)
        ]

    async def list_output_files(self, session_id: str) -> list[OutputFileInfo]:
        return [
            OutputFileInfo(file.id, file.filename)
            async for file in self._client.beta.files.list(
                scope_id=session_id, betas=["managed-agents-2026-04-01"]
            )
        ]

    async def download_file(self, file_id: str, dest: Path) -> None:
        content = await self._client.files.download(file_id)
        await content.write_to_file(dest)
