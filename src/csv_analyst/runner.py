"""Run one budgeted, file-backed Managed Agents session."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from csv_analyst.events import ProgressEvent, is_terminal, normalize
from csv_analyst.outputs import collect_followup, next_followup_index
from csv_analyst.platform import PlatformNotFound, SessionInfo, SessionPlatform
from csv_analyst.prompts import build_followup_message, build_user_message

RunStatus = Literal["completed", "paused_budget", "requires_action", "failed"]


async def _interrupt_cancelled(platform: SessionPlatform, session_id: str) -> None:
    """Best effort: leave a cancelled local command without a running remote turn."""
    try:
        await asyncio.wait_for(platform.send_interrupt(session_id), timeout=5)
    except Exception:
        pass


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    status: RunStatus
    stop_reason: str
    list_cost_cents: int | None
    error_types: tuple[str, ...]
    agent_version: int | None = None
    model: str | None = None
    skill_ids: tuple[str, ...] = ()
    active_seconds: float | None = None


def session_artifact_dir(session: SessionInfo, root: Path = Path("runs")) -> Path:
    """Resolve a session's original folder from trusted metadata and title."""
    metadata = session.metadata or {}
    run_id = metadata.get("run_id", "")
    title = session.title or ""
    if metadata.get("app") != "csv-analyst" or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id
    ):
        raise ValueError("Session is not an owned csv-analyst run")
    if not title.startswith("csv-analyst: "):
        raise ValueError("Session title does not identify a CSV input")
    input_name = title.removeprefix("csv-analyst: ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.csv", input_name):
        raise ValueError("Session title has an invalid CSV filename")
    return root / run_id / Path(input_name).stem


def _local_artifact_dirs(session: SessionInfo, root: Path) -> tuple[Path, ...]:
    """Include the Phase 5 resume folder for sessions completed before this fix."""
    primary = session_artifact_dir(session, root)
    if re.fullmatch(r"[A-Za-z0-9_-]+", session.id) is None:
        return (primary,)
    legacy = root / f"resumed-{session.id}" / primary.name
    return (primary, legacy)


async def run_session(
    platform: SessionPlatform,
    input_path: Path,
    agent_id: str,
    environment_id: str,
    run_id: str,
    *,
    budget_cents: int | None,
    timeout_s: int,
    agent_version: int | None = None,
    model: str | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
    raw_sink: Callable[[dict[str, Any]], None] | None = None,
) -> SessionResult:
    if budget_cents is not None and budget_cents <= 0:
        raise ValueError("budget_cents must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if agent_version is not None and agent_version <= 0:
        raise ValueError("agent_version must be positive")
    if model is not None and not model.strip():
        raise ValueError("model must be non-empty")
    if not input_path.is_file() or input_path.suffix.lower() != ".csv":
        raise ValueError("Input must be an existing CSV file")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.csv", input_path.name) is None:
        raise ValueError(
            "CSV filename must use letters, digits, dots, underscores, or dashes"
        )

    file_id = await platform.upload_file(input_path)
    session = await platform.create_session(
        agent_id,
        environment_id,
        file_id,
        input_path.name,
        budget_cents,
        run_id,
        agent_version=agent_version,
        model=model,
    )
    try:
        stream = await platform.open_event_stream(session.id)
    except asyncio.CancelledError:
        await _interrupt_cancelled(platform, session.id)
        raise
    reason: str | None = None
    cost: int | None = None
    active_seconds: float | None = None
    errors: list[str] = []
    try:
        try:
            async with asyncio.timeout(timeout_s):
                await platform.send_message(
                    session.id,
                    build_user_message(input_path.name, input_path.stem, run_id),
                )
                async for raw in stream:
                    if raw_sink is not None:
                        raw_sink(raw)
                    if raw.get("type") == "session.usage":
                        usage = raw.get("usage")
                        if isinstance(usage, dict) and isinstance(
                            usage.get("active_seconds"), (int, float)
                        ):
                            active_seconds = float(usage["active_seconds"])
                    progress = normalize(
                        raw, session_id=session.id, label=input_path.stem
                    )
                    if progress is not None:
                        if progress.list_cost_cents is not None:
                            cost = progress.list_cost_cents
                        if progress.kind == "error":
                            errors.append(progress.text)
                        if sink is not None:
                            sink(progress)
                    terminal, outcome = is_terminal(raw)
                    if terminal:
                        reason = outcome
                        break
        except TimeoutError:
            reason = "timeout"
            await platform.send_interrupt(session.id)
        except asyncio.CancelledError:
            await _interrupt_cancelled(platform, session.id)
            raise
    finally:
        await stream.close()

    if reason == "end_turn":
        status: RunStatus = "completed"
    elif reason == "budget_reached":
        status = "paused_budget"
    elif reason == "requires_action":
        status = "requires_action"
    else:
        status = "failed"
    return SessionResult(
        session.id,
        status,
        reason or "stream_ended",
        cost,
        tuple(errors),
        session.agent_version,
        session.model,
        session.skill_ids,
        active_seconds,
    )


async def resume_budget_session(
    platform: SessionPlatform,
    session_id: str,
    to_cents: int,
    *,
    timeout_s: int,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> SessionResult:
    """Raise an existing cap and consume the automatically resumed work."""
    if to_cents <= 0 or timeout_s <= 0:
        raise ValueError("Budget and timeout must be positive")
    session = await platform.retrieve_session(session_id)
    if session.status != "idle" or session.budget_cents is None:
        raise ValueError("Session must be idle with an existing budget")
    if session.list_cost_cents is None or to_cents <= session.list_cost_cents + 1:
        raise ValueError("New cap must exceed consumed list cost by more than one cent")
    events = await platform.list_events(session_id)
    idle = next(
        (
            event
            for event in reversed(events)
            if event.get("type") == "session.status_idle"
        ),
        None,
    )
    stop = idle.get("stop_reason") if idle is not None else None
    if not isinstance(stop, dict) or stop.get("type") != "budget_reached":
        raise ValueError("Session is not paused at its budget")

    try:
        stream = await platform.open_event_stream(session_id)
    except asyncio.CancelledError:
        await _interrupt_cancelled(platform, session_id)
        raise
    reason: str | None = None
    cost = session.list_cost_cents
    active_seconds = session.active_seconds
    errors: list[str] = []
    try:
        try:
            async with asyncio.timeout(timeout_s):
                await platform.update_session_budget(session_id, to_cents)
                async for raw in stream:
                    if raw.get("type") == "session.usage":
                        usage = raw.get("usage")
                        if isinstance(usage, dict) and isinstance(
                            usage.get("active_seconds"), (int, float)
                        ):
                            active_seconds = float(usage["active_seconds"])
                    progress = normalize(raw, session_id=session_id, label=session_id)
                    if progress is not None:
                        if progress.list_cost_cents is not None:
                            cost = progress.list_cost_cents
                        if progress.kind == "error":
                            errors.append(progress.text)
                        if sink is not None:
                            sink(progress)
                    terminal, outcome = is_terminal(raw)
                    if terminal:
                        reason = outcome
                        break
        except TimeoutError:
            reason = "timeout"
            await platform.send_interrupt(session_id)
        except asyncio.CancelledError:
            await _interrupt_cancelled(platform, session_id)
            raise
    finally:
        await stream.close()
    if reason == "end_turn":
        status: RunStatus = "completed"
    elif reason == "budget_reached":
        status = "paused_budget"
    elif reason == "requires_action":
        status = "requires_action"
    else:
        status = "failed"
    return SessionResult(
        session_id,
        status,
        reason or "stream_ended",
        cost,
        tuple(errors),
        session.agent_version,
        session.model,
        session.skill_ids,
        active_seconds,
    )


async def ask_session(
    platform: SessionPlatform,
    session_id: str,
    question: str,
    *,
    timeout_s: int,
    output_root: Path = Path("runs"),
    sink: Callable[[ProgressEvent], None] | None = None,
) -> tuple[SessionResult, tuple[Path, ...]]:
    """Continue an idle turn and collect its uniquely prefixed artifacts."""
    if timeout_s <= 0 or not question.strip():
        raise ValueError("Provide a question and positive timeout")
    session = await platform.retrieve_session(session_id)
    if session.status != "idle":
        raise ValueError("Session must be idle before asking a follow-up")
    if session.created_at is not None and datetime.now(
        UTC
    ) - session.created_at >= timedelta(days=30):
        raise ValueError(
            "This session's sandbox is at least 30 days old and its files may be gone. "
            "Start a new run instead of relying on the old analysis.py."
        )
    destination = session_artifact_dir(session, output_root)
    history = await platform.list_events(session_id)
    last_idle = next(
        (
            event
            for event in reversed(history)
            if event.get("type") == "session.status_idle"
        ),
        None,
    )
    if last_idle is not None:
        stop = last_idle.get("stop_reason")
        if isinstance(stop, dict) and stop.get("type") == "budget_reached":
            raise ValueError("Session is at its budget; use raise-budget first")
        if isinstance(stop, dict) and stop.get("type") == "requires_action":
            raise ValueError("Session requires action before a follow-up")
    index = next_followup_index(
        await platform.list_output_files(session_id), destination
    )
    try:
        stream = await platform.open_event_stream(session_id)
    except asyncio.CancelledError:
        await _interrupt_cancelled(platform, session_id)
        raise
    reason: str | None = None
    cost = session.list_cost_cents
    active_seconds = session.active_seconds
    errors: list[str] = []
    try:
        try:
            async with asyncio.timeout(timeout_s):
                await platform.send_message(
                    session_id, build_followup_message(question, index)
                )
                async for raw in stream:
                    if raw.get("type") == "session.usage":
                        usage = raw.get("usage")
                        if isinstance(usage, dict) and isinstance(
                            usage.get("active_seconds"), (int, float)
                        ):
                            active_seconds = float(usage["active_seconds"])
                    progress = normalize(
                        raw, session_id=session_id, label=destination.name
                    )
                    if progress is not None:
                        if progress.list_cost_cents is not None:
                            cost = progress.list_cost_cents
                        if progress.kind == "error":
                            errors.append(progress.text)
                        if sink is not None:
                            sink(progress)
                    terminal, outcome = is_terminal(raw)
                    if terminal:
                        reason = outcome
                        break
        except TimeoutError:
            reason = "timeout"
            await platform.send_interrupt(session_id)
        except asyncio.CancelledError:
            await _interrupt_cancelled(platform, session_id)
            raise
    finally:
        await stream.close()
    status: RunStatus = (
        "completed"
        if reason == "end_turn"
        else "paused_budget"
        if reason == "budget_reached"
        else "requires_action"
        if reason == "requires_action"
        else "failed"
    )
    files: tuple[Path, ...] = ()
    if status == "completed":
        files = await collect_followup(platform, session_id, destination, index)
    return (
        SessionResult(
            session_id,
            status,
            reason or "stream_ended",
            cost,
            tuple(errors),
            session.agent_version,
            session.model,
            session.skill_ids,
            active_seconds,
        ),
        files,
    )


async def tail_session(
    platform: SessionPlatform,
    session_id: str,
    *,
    follow: bool = False,
    sink: Callable[[ProgressEvent], None],
) -> None:
    """Open the stream before history and render every persisted ID once."""
    stream = await platform.open_event_stream(session_id)
    seen: set[str] = set()
    history: list[dict[str, Any]] = []

    def emit(raw: dict[str, Any]) -> None:
        progress = normalize(raw, session_id=session_id, label=session_id)
        if progress is None:
            raw_type = str(raw.get("type", "event"))
            content = raw.get("content")
            if raw_type == "user.message" and isinstance(content, list):
                message = " ".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
                detail = " ".join(message.split())[:300]
            else:
                detail = raw_type
            progress = ProgressEvent(
                session_id,
                session_id,
                "status",
                detail,
                raw_type=raw_type,
                event_id=raw.get("id") if isinstance(raw.get("id"), str) else None,
            )
        sink(progress)

    try:

        def emit_unseen(events: list[dict[str, Any]]) -> None:
            for raw in events:
                event_id = raw.get("id")
                if not isinstance(event_id, str) or event_id in seen:
                    continue
                seen.add(event_id)
                emit(raw)

        history = await platform.list_events(session_id)
        emit_unseen(history)
        session = await platform.retrieve_session(session_id)
        if session.status == "terminated" or (session.status == "idle" and not follow):
            # The turn may have idled after the first history snapshot. Fetch once
            # more before deciding whether the already-open stream needs draining.
            history = await platform.list_events(session_id)
            emit_unseen(history)
            transitions = [
                raw.get("type")
                for raw in history
                if raw.get("type")
                in {
                    "user.message",
                    "session.status_running",
                    "session.status_idle",
                    "session.status_terminated",
                }
            ]
            if not transitions or transitions[-1] in {
                "session.status_idle",
                "session.status_terminated",
            }:
                return
        async for raw in stream:
            event_id = raw.get("id")
            if not isinstance(event_id, str) or event_id in seen:
                continue
            seen.add(event_id)
            emit(raw)
            terminal, _ = is_terminal(raw)
            if terminal and (
                not follow or raw.get("type") == "session.status_terminated"
            ):
                break
    finally:
        await stream.close()


@dataclass(frozen=True)
class CleanupOutcome:
    session_id: str
    action: str
    detail: str


def _outputs_complete(
    destinations: tuple[Path, ...],
    remote_names: set[str],
    history: list[dict[str, Any]],
) -> bool:
    """Require one locally complete output set for every submitted turn."""

    def local_file(name: str) -> Path | None:
        return next(
            (
                path
                for directory in destinations
                if (path := directory / name).is_file() and not path.is_symlink()
            ),
            None,
        )

    if not remote_names or any(Path(name).name != name for name in remote_names):
        return False
    if not {"report.md", "analysis.py", "manifest.json"} <= remote_names:
        return False
    if not all(local_file(name) is not None for name in remote_names):
        return False
    followup_manifests = {
        path.name: path
        for directory in reversed(destinations)
        for path in directory.glob("followup_*_manifest.json")
        if path.is_file() and not path.is_symlink()
    }
    turn_count = sum(event.get("type") == "user.message" for event in history)
    if turn_count != 1 + len(followup_manifests):
        return False
    try:
        base_path = local_file("manifest.json")
        if base_path is None:
            return False
        base = json.loads(base_path.read_text(encoding="utf-8"))
        charts = base.get("charts") if isinstance(base, dict) else None
        if not isinstance(charts, list) or not charts:
            return False
        manifests: list[tuple[str, object]] = [("manifest.json", charts)]
        for manifest in followup_manifests.values():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            names = data.get("files") if isinstance(data, dict) else None
            manifests.append((manifest.name, names))
        for manifest_name, names in manifests:
            if manifest_name not in remote_names or not isinstance(names, list):
                return False
            if not all(
                isinstance(name, str)
                and name in remote_names
                and local_file(name) is not None
                for name in names
            ):
                return False
    except (OSError, json.JSONDecodeError):
        return False
    return True


async def cleanup_run(
    platform: SessionPlatform,
    run_id: str,
    *,
    delete: bool = False,
    output_root: Path = Path("runs"),
) -> list[CleanupOutcome]:
    """Archive one recorded run, or delete only fully downloaded sessions."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None:
        raise ValueError("Invalid run ID")
    summary_path = output_root / run_id / "summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read run summary at {summary_path}") from exc
    if not isinstance(summary, dict) or summary.get("run_id") != run_id:
        raise ValueError("Run summary does not match the requested run")
    rows = summary.get("sessions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Run summary has no sessions")
    identifiers = [row.get("session_id") for row in rows if isinstance(row, dict)]
    if (
        len(identifiers) != len(rows)
        or not all(isinstance(value, str) and value for value in identifiers)
        or len(set(identifiers)) != len(identifiers)
    ):
        raise ValueError("Run summary has invalid session IDs")
    outcomes: list[CleanupOutcome] = []
    for session_id in identifiers:
        assert isinstance(session_id, str)
        try:
            session = await platform.retrieve_session(session_id)
        except PlatformNotFound:
            outcomes.append(
                CleanupOutcome(
                    session_id, "already_removed", "session no longer exists"
                )
            )
            continue
        metadata = session.metadata or {}
        if metadata.get("app") != "csv-analyst" or metadata.get("run_id") != run_id:
            outcomes.append(CleanupOutcome(session_id, "skipped", "foreign metadata"))
            continue
        if session.status in {"running", "rescheduling"}:
            outcomes.append(
                CleanupOutcome(
                    session_id,
                    "skipped",
                    f"{session.status}; send user.interrupt and wait for idle",
                )
            )
            continue
        if delete:
            try:
                destinations = _local_artifact_dirs(session, output_root)
                remote_files = await platform.list_output_files(session_id)
                names = {file.filename for file in remote_files}
                history = await platform.list_events(session_id)
                if not _outputs_complete(destinations, names, history):
                    raise ValueError("local outputs are missing or incomplete")
            except ValueError as exc:
                outcomes.append(CleanupOutcome(session_id, "skipped", str(exc)))
                continue
            await platform.delete_session(session_id)
            outcomes.append(
                CleanupOutcome(session_id, "deleted", "local outputs verified")
            )
        elif session.status == "terminated":
            outcomes.append(CleanupOutcome(session_id, "skipped", "already terminated"))
        else:
            await platform.archive_session(session_id)
            outcomes.append(CleanupOutcome(session_id, "archived", "history retained"))
    return outcomes
