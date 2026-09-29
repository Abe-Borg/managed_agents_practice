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
    errors: list[str] = []
    try:
        try:
            async with asyncio.timeout(timeout_s):
                await platform.send_message(
                    session.id, build_user_message(input_path.name, input_path.stem)
                )
                async for raw in stream:
                    if raw_sink is not None:
                        raw_sink(raw)
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
    )
