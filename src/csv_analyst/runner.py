"""Run one budgeted, file-backed Managed Agents session."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from csv_analyst.events import ProgressEvent, is_terminal, normalize
from csv_analyst.platform import SessionPlatform
from csv_analyst.prompts import build_user_message

RunStatus = Literal["completed", "paused_budget", "requires_action", "failed"]


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
    stream = await platform.open_event_stream(session.id)
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

    stream = await platform.open_event_stream(session_id)
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
