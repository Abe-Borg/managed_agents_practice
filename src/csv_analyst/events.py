"""Turn raw Managed Agents events into concise application progress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProgressKind = Literal[
    "status", "message", "tool_use", "tool_result", "usage", "error", "done"
]


@dataclass(frozen=True)
class ProgressEvent:
    session_id: str
    label: str
    kind: ProgressKind
    text: str
    tool_name: str | None = None
    stop_reason: str | None = None
    list_cost_cents: int | None = None
    raw_type: str = ""
    event_id: str | None = None


def _short(value: object) -> str:
    return " ".join(str(value).split())[:300]


def _cost(raw: dict[str, Any]) -> int | None:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None
    list_cost = usage.get("list_cost")
    if not isinstance(list_cost, dict):
        return None
    amount = list_cost.get("amount")
    if not isinstance(amount, (str, int)):
        return None
    try:
        return int(amount)
    except (TypeError, ValueError):
        return None


def is_terminal(raw: dict[str, Any]) -> tuple[bool, str | None]:
    raw_type = raw.get("type")
    if raw_type == "session.status_terminated":
        return True, "terminated"
    if raw_type == "session.status_idle":
        reason = raw.get("stop_reason")
        if isinstance(reason, dict):
            kind = reason.get("type")
            if kind in {
                "end_turn",
                "budget_reached",
                "retries_exhausted",
                "requires_action",
            }:
                return True, kind
    return False, None


def normalize(
    raw: dict[str, Any], *, session_id: str, label: str
) -> ProgressEvent | None:
    raw_type = raw.get("type")
    if (
        not isinstance(raw_type, str)
        or raw_type.startswith("span.")
        or raw_type
        in {
            "event_start",
            "event_delta",
            "agent.thinking",
        }
    ):
        return None
    event_id = raw.get("id") if isinstance(raw.get("id"), str) else None

    def make(
        kind: ProgressKind,
        text: str,
        *,
        tool_name: str | None = None,
        stop_reason: str | None = None,
        list_cost_cents: int | None = None,
    ) -> ProgressEvent:
        return ProgressEvent(
            session_id=session_id,
            label=label,
            kind=kind,
            text=text,
            tool_name=tool_name,
            stop_reason=stop_reason,
            list_cost_cents=list_cost_cents,
            raw_type=raw_type,
            event_id=event_id,
        )

    if raw_type == "agent.message":
        content = raw.get("content")
        text = (
            " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if isinstance(content, list)
            else ""
        )
        return make("message", _short(text))
    if raw_type == "agent.tool_use":
        name = raw.get("name") if isinstance(raw.get("name"), str) else "tool"
        tool_input = raw.get("input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return make(
            "tool_use", _short(command if command is not None else name), tool_name=name
        )
    if raw_type == "agent.tool_result":
        return make("tool_result", "Tool finished")
    if raw_type == "session.usage":
        cents = _cost(raw)
        return make(
            "usage",
            f"List cost: {cents}¢" if cents is not None else "Usage updated",
            list_cost_cents=cents,
        )
    if raw_type == "session.error":
        error = raw.get("error")
        error_type = error.get("type") if isinstance(error, dict) else "unknown"
        return make("error", _short(error_type))
    terminal, reason = is_terminal(raw)
    if terminal:
        return make("done", f"Stopped: {reason}", stop_reason=reason)
    if raw_type.startswith("session.status_"):
        return make("status", _short(raw_type.removeprefix("session.")))
    return None
