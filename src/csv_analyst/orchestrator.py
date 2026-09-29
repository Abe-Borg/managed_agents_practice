"""Concurrent CSV sessions, isolation checks, and durable run summaries."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from csv_analyst.events import ProgressEvent
from csv_analyst.outputs import OutputError, collect
from csv_analyst.platform import SessionPlatform
from csv_analyst.runner import run_session


@dataclass
class SessionOutcome:
    label: str
    input_file: str
    session_id: str | None
    status: str
    stop_reason: str
    list_cost_cents: int | None
    active_seconds: float | None
    artifacts_path: str | None
    started_at: str
    ended_at: str
    isolation: bool | None
    error: str | None = None
    agent_version: int | None = None
    model: str | None = None
    skill_ids: tuple[str, ...] = ()


@dataclass
class RunSummary:
    run_id: str
    sessions: list[SessionOutcome]

    @property
    def total_list_cost_cents(self) -> int:
        return sum(item.list_cost_cents or 0 for item in self.sessions)

    @property
    def isolation_passed(self) -> bool:
        return all(
            item.isolation is True
            for item in self.sessions
            if item.status == "completed"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sessions": [asdict(item) for item in self.sessions],
            "total_list_cost_cents": self.total_list_cost_cents,
            "isolation_passed": self.isolation_passed,
        }

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "summary.json"
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target


def check_isolation(
    manifest: dict[str, Any], input_name: str, *, require_exclusive: bool = True
) -> bool:
    """The exclusive run marker also detects a shared filesystem without a race."""
    return (
        manifest.get("input_file") == input_name
        and manifest.get("uploads_seen") == [input_name]
        and manifest.get("markers_seen_before_write") == []
        and (not require_exclusive or manifest.get("exclusive_marker_created") is True)
    )


async def run_many(
    files: Sequence[Path],
    platform_factory: Callable[[], SessionPlatform],
    agent_id: str,
    environment_id: str,
    run_id: str,
    *,
    budget_cents: int | None,
    timeout_s: int,
    max_parallel: int,
    output_root: Path,
    agent_version: int | None = None,
    model: str | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
    raw_sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> RunSummary:
    if not files or max_parallel <= 0:
        raise ValueError("Provide CSV files and a positive max_parallel")
    stems = [path.stem.casefold() for path in files]
    if len(set(stems)) != len(stems):
        raise ValueError(
            "CSV input stems must be distinct to avoid artifact collisions"
        )
    semaphore = asyncio.Semaphore(max_parallel)

    async def one(path: Path) -> SessionOutcome:
        async with semaphore:
            started = datetime.now(UTC).isoformat()
            platform: SessionPlatform | None = None
            session_id: str | None = None
            cost: int | None = None
            active: float | None = None
            status = "failed"
            reason = "error"
            artifacts: str | None = None
            isolation: bool | None = None
            error: str | None = None
            agent_version_resolved: int | None = None
            resolved_model: str | None = None
            skills: tuple[str, ...] = ()
            try:
                platform = platform_factory()
                result = await run_session(
                    platform,
                    path,
                    agent_id,
                    environment_id,
                    run_id,
                    budget_cents=budget_cents,
                    timeout_s=timeout_s,
                    agent_version=agent_version,
                    model=model,
                    sink=sink,
                    raw_sink=(
                        (lambda raw: raw_sink(path.stem, raw))
                        if raw_sink is not None
                        else None
                    ),
                )
                session_id = result.session_id
                cost = result.list_cost_cents
                active = result.active_seconds
                status = result.status
                reason = result.stop_reason
                agent_version_resolved = result.agent_version
                resolved_model = result.model
                skills = result.skill_ids
                if result.status == "completed":
                    collected = await collect(
                        platform,
                        session_id,
                        output_root / path.stem,
                        path.name,
                    )
                    artifacts = str(collected.directory)
                    isolation = check_isolation(
                        collected.manifest, path.name, require_exclusive=len(files) > 1
                    )
                    if not isolation:
                        status = "failed"
                        reason = "isolation_failed"
                        error = "Isolation proof failed"
            except OutputError as exc:
                error = str(exc)
                status = "failed"
                reason = (
                    "isolation_failed"
                    if (
                        "unexpected uploads" in error
                        or "unexpected sandbox markers" in error
                    )
                    else "output_error"
                )
                isolation = False if reason == "isolation_failed" else None
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            finally:
                if platform is not None:
                    try:
                        await platform.close()
                    except Exception as exc:
                        if error is None:
                            error = f"{type(exc).__name__}: {exc}"
                            status = "failed"
                            reason = "close_error"
            return SessionOutcome(
                label=path.stem,
                input_file=path.name,
                session_id=session_id,
                status=status,
                stop_reason=reason,
                list_cost_cents=cost,
                active_seconds=active,
                artifacts_path=artifacts,
                started_at=started,
                ended_at=datetime.now(UTC).isoformat(),
                isolation=isolation,
                error=error,
                agent_version=agent_version_resolved,
                model=resolved_model,
                skill_ids=skills,
            )

    outcomes = list(await asyncio.gather(*(one(path) for path in files)))
    ids = [item.session_id for item in outcomes if item.session_id is not None]
    duplicates = {item for item in ids if ids.count(item) > 1}
    for item in outcomes:
        if item.session_id in duplicates:
            item.isolation = False
            item.status = "failed"
            item.stop_reason = "isolation_failed"
            item.error = "Duplicate session ID"
    summary = RunSummary(run_id, outcomes)
    summary.save(output_root)
    return summary
