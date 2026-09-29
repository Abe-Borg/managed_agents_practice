from __future__ import annotations

import json
from pathlib import Path

import pytest

from csv_analyst.events import is_terminal, normalize

FIXTURES = Path(__file__).parent / "fixtures" / "events"


@pytest.mark.parametrize("name", ["tiny_end_turn.jsonl", "budget_reached.jsonl"])
def test_synthetic_stream_fixtures_normalize_and_end(name: str) -> None:
    events = [json.loads(line) for line in (FIXTURES / name).read_text().splitlines()]
    normalized = [
        normalize(event, session_id="sesn_1", label="tiny") for event in events
    ]
    assert len(normalized) == len(events)
    assert all(event is None or event.session_id == "sesn_1" for event in normalized)
    assert is_terminal(events[-1]) == (
        True,
        "budget_reached" if name.startswith("budget") else "end_turn",
    )


def test_ignored_deltas_and_errors() -> None:
    assert normalize({"type": "event_delta"}, session_id="s", label="tiny") is None
    error = normalize(
        {"type": "session.error", "error": {"type": "model_overloaded"}},
        session_id="s",
        label="tiny",
    )
    assert error is not None and error.kind == "error"
    assert error.text == "model_overloaded"
