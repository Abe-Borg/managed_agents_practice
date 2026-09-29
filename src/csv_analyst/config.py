"""Local configuration with no API calls or secret logging."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_BUDGET_CENTS = 100
DEFAULT_MAX_PARALLEL = 3
DEFAULT_TIMEOUT_S = 600
_PLACEHOLDER_KEY = "sk-ant-REPLACE_ME"


def _positive_int(source: Mapping[str, str | None], name: str, default: int) -> int:
    raw = source.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw.isdecimal() or int(raw) <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(raw)


@dataclass(frozen=True, repr=False)
class Settings:
    api_key: str | None
    model: str
    budget_cents: int
    max_parallel: int
    timeout_s: int

    @property
    def display_model(self) -> str:
        """Return a model label safe to include in diagnostics."""
        if self.api_key:
            return self.model.replace(self.api_key, "<redacted>")
        return self.model

    def __repr__(self) -> str:
        key_display = "<redacted>" if self.api_key else "None"
        return (
            "Settings("
            f"api_key={key_display}, "
            f"model={self.display_model!r}, "
            f"budget_cents={self.budget_cents!r}, "
            f"max_parallel={self.max_parallel!r}, "
            f"timeout_s={self.timeout_s!r}"
            ")"
        )


def load_settings(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = Path(".env"),
) -> Settings:
    """Read .env, then overlay the process environment or a supplied test mapping."""
    source: dict[str, str | None] = {}
    if dotenv_path is not None:
        source.update(dotenv_values(dotenv_path, interpolate=False))
    source.update(os.environ if env is None else env)

    raw_key = (source.get("ANTHROPIC_API_KEY") or "").strip()
    api_key = raw_key if raw_key and raw_key != _PLACEHOLDER_KEY else None
    raw_model = source.get("CSV_ANALYST_MODEL")
    model = DEFAULT_MODEL if raw_model is None else raw_model.strip()
    if not model:
        raise ValueError("CSV_ANALYST_MODEL must be non-empty")

    return Settings(
        api_key=api_key,
        model=model,
        budget_cents=_positive_int(
            source, "CSV_ANALYST_BUDGET_CENTS", DEFAULT_BUDGET_CENTS
        ),
        max_parallel=_positive_int(
            source, "CSV_ANALYST_MAX_PARALLEL", DEFAULT_MAX_PARALLEL
        ),
        timeout_s=_positive_int(source, "CSV_ANALYST_TIMEOUT_S", DEFAULT_TIMEOUT_S),
    )
