"""Collect only the expected flat artifacts from one session."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from csv_analyst.platform import OutputFileInfo, SessionPlatform

_CHART = re.compile(r"chart_[0-9]{2}_[a-z0-9_-]+\.png\Z")
_BASE = {"report.md", "analysis.py", "manifest.json"}


class OutputError(ValueError):
    """Expected artifacts are missing or their manifest is invalid."""


@dataclass(frozen=True)
class CollectedOutputs:
    directory: Path
    files: tuple[Path, ...]
    manifest: dict[str, Any]
    ignored: tuple[str, ...]


def _validate_manifest(data: Any, input_name: str) -> list[str]:
    if not isinstance(data, dict):
        raise OutputError("manifest.json must contain a JSON object")
    if data.get("input_file") != input_name:
        raise OutputError("manifest.json names the wrong input file")
    if data.get("uploads_seen") != [input_name]:
        raise OutputError("manifest.json reports unexpected uploads")
    markers = data.get("markers_seen_before_write")
    if markers != []:
        raise OutputError("manifest.json reports unexpected sandbox markers")
    for field in ("rows", "columns"):
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise OutputError(f"manifest.json has an invalid {field}")
    if not isinstance(data.get("summary"), str):
        raise OutputError("manifest.json has no summary")
    charts = data.get("charts")
    if (
        not isinstance(charts, list)
        or not 1 <= len(charts) <= 4
        or not all(isinstance(name, str) and _CHART.fullmatch(name) for name in charts)
        or len(set(charts)) != len(charts)
    ):
        raise OutputError("manifest.json has invalid chart filenames")
    return charts


async def collect(
    platform: SessionPlatform,
    session_id: str,
    dest: Path,
    input_name: str,
    *,
    max_wait_s: float = 30,
    poll_s: float = 2,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CollectedOutputs:
    """Poll for the manifest, then all named outputs, and download them."""
    if max_wait_s < 0 or poll_s < 0:
        raise ValueError("Polling intervals must be nonnegative")
    dest.mkdir(parents=True, exist_ok=True)
    deadline = monotonic() + max_wait_s
    manifest: dict[str, Any] | None = None
    required = set(_BASE)
    listed: dict[str, OutputFileInfo] = {}
    ignored: set[str] = set()

    while True:
        for file in await platform.list_output_files(session_id):
            name = Path(file.filename).name
            if name == file.filename and (name in _BASE or _CHART.fullmatch(name)):
                listed[name] = file
            else:
                ignored.add(file.filename)
        if manifest is None and "manifest.json" in listed:
            await platform.download_file(
                listed["manifest.json"].id, dest / "manifest.json"
            )
            try:
                parsed = json.loads(
                    (dest / "manifest.json").read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise OutputError("manifest.json is not valid JSON") from exc
            charts = _validate_manifest(parsed, input_name)
            manifest = parsed
            required.update(charts)
        if manifest is not None and required <= listed.keys():
            break
        if monotonic() >= deadline:
            missing = ", ".join(sorted(required - listed.keys()))
            raise OutputError(f"Timed out waiting for session artifacts: {missing}")
        await sleep(poll_s)

    ignored.update(name for name in listed if name not in required)
    files: list[Path] = [dest / "manifest.json"]
    for name in sorted(required - {"manifest.json"}):
        target = dest / name
        await platform.download_file(listed[name].id, target)
        files.append(target)
    return CollectedOutputs(dest, tuple(files), manifest, tuple(sorted(ignored)))
