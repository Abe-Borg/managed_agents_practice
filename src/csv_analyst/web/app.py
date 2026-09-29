"""Loopback-only web API, with in-process event replay for each run."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from markdown_it import MarkdownIt
from pydantic import BaseModel
from pydantic import Field as PydanticField

from csv_analyst.config import Settings, load_settings
from csv_analyst.events import ProgressEvent
from csv_analyst.orchestrator import RunSummary, run_many
from csv_analyst.outputs import collect
from csv_analyst.platform import SdkSessionPlatform, SessionPlatform
from csv_analyst.resources import load_state
from csv_analyst.runner import ask_session, resume_budget_session, session_artifact_dir

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.csv\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_ARTIFACT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_FILE_ID = re.compile(r"\bfile_[A-Za-z0-9_-]+\b")
_KEY_PATTERN = re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b")
_MAX_FILE = 1024 * 1024
_MAX_EVENTS = 10000
_WEB_DIR = Path(__file__).parent


class AskBody(BaseModel):
    question: str = PydanticField(min_length=1, max_length=4000)


class BudgetBody(BaseModel):
    to_cents: int = PydanticField(ge=1, le=500)


@dataclass
class RunChannel:
    run_id: str
    labels: list[str]
    events: list[tuple[int, ProgressEvent]] = field(default_factory=list)
    subscribers: set[asyncio.Queue[tuple[int, ProgressEvent]]] = field(
        default_factory=set
    )
    summary: RunSummary | None = None
    allowed: dict[str, set[str]] = field(default_factory=dict)
    busy_sessions: set[str] = field(default_factory=set)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    next_id: int = 1
    failure: str | None = None

    def publish(self, event: ProgressEvent) -> None:
        entry = (self.next_id, event)
        self.next_id += 1
        self.events.append(entry)
        if len(self.events) > _MAX_EVENTS:
            del self.events[: len(self.events) - _MAX_EVENTS]
        for queue in tuple(self.subscribers):
            if queue.full():
                self.subscribers.discard(queue)
            else:
                queue.put_nowait(entry)

    def launch(self, coro: Any) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


def _redact(value: Any, key: str | None) -> Any:
    if isinstance(value, str):
        if key:
            value = value.replace(key, "<redacted>")
        return _FILE_ID.sub("<file-id>", _KEY_PATTERN.sub("<redacted>", value))
    if isinstance(value, dict):
        return {name: _redact(item, key) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, key) for item in value]
    return value


def _initial_artifacts(directory: Path) -> set[str]:
    manifest = directory / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    charts = data.get("charts") if isinstance(data, dict) else None
    if not isinstance(charts, list):
        return set()
    names = {"report.md", "analysis.py", "manifest.json"}
    for name in charts:
        if isinstance(name, str) and re.fullmatch(
            r"chart_[0-9]{2}_[a-z0-9_-]+\.png", name
        ):
            names.add(name)
    return {name for name in names if (directory / name).is_file()}


def create_app(
    *,
    settings: Settings | None = None,
    platform_factory: Callable[[], SessionPlatform] | None = None,
    output_root: Path = Path("runs"),
    agent_id: str | None = None,
    environment_id: str | None = None,
) -> FastAPI:
    """Build a single-user local server; injection points keep offline tests offline."""
    config = settings or load_settings()
    saved = load_state() if agent_id is None or environment_id is None else None
    agent = agent_id or (saved.agent_id if saved else None)
    environment = environment_id or (saved.environment_id if saved else None)
    if platform_factory is None:
        if config.api_key is None:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set; add it to the environment or ignored .env"
            )

        def platform_factory() -> SessionPlatform:
            return SdkSessionPlatform(config.api_key or "")

    if agent is None or environment is None:
        raise ValueError("Run csv-analyst setup first")

    app = FastAPI(title="csv-analyst local UI")
    runs: dict[str, RunChannel] = {}
    sessions: dict[str, RunChannel] = {}
    app.state.runs = runs

    def channel_for(run_id: str) -> RunChannel:
        if not _ID.fullmatch(run_id) or run_id not in runs:
            raise HTTPException(404, "Run not found")
        return runs[run_id]

    def session_for(session_id: str) -> RunChannel:
        channel = sessions.get(session_id)
        if channel is None:
            raise HTTPException(404, "Session not found")
        return channel

    def safe_event(channel: RunChannel, event: ProgressEvent) -> None:
        data = _redact(asdict(event), config.api_key)
        channel.publish(ProgressEvent(**data))

    def require_local_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is None:
            return
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port != request.url.port
        ):
            raise HTTPException(403, "Cross-origin requests are not allowed")

    async def run_job(
        channel: RunChannel,
        paths: list[Path],
        temp: tempfile.TemporaryDirectory[str],
        cap: int,
    ) -> None:
        try:
            summary = await run_many(
                paths,
                platform_factory,
                agent,
                environment,
                channel.run_id,
                budget_cents=cap,
                timeout_s=config.timeout_s,
                max_parallel=min(config.max_parallel, len(paths)),
                output_root=output_root / channel.run_id,
                sink=lambda event: safe_event(channel, event),
            )
            channel.summary = summary
            for outcome in summary.sessions:
                if outcome.session_id is not None:
                    sessions[outcome.session_id] = channel
                if outcome.artifacts_path is not None:
                    channel.allowed[outcome.label] = _initial_artifacts(
                        output_root / channel.run_id / outcome.label
                    )
                if not any(
                    event.label == outcome.label and event.kind == "done"
                    for _, event in channel.events
                ):
                    safe_event(
                        channel,
                        ProgressEvent(
                            outcome.session_id or "",
                            outcome.label,
                            "done",
                            outcome.stop_reason,
                            stop_reason=outcome.stop_reason,
                        ),
                    )
        except Exception as exc:
            channel.failure = _redact(f"{type(exc).__name__}: {exc}", config.api_key)
            for label in channel.labels:
                safe_event(channel, ProgressEvent("", label, "error", channel.failure))
                safe_event(
                    channel,
                    ProgressEvent("", label, "done", "failed", stop_reason="error"),
                )
        finally:
            temp.cleanup()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__DEFAULT_BUDGET__", str(min(config.budget_cents, 500)))
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/app.js")
    async def javascript() -> FileResponse:
        return FileResponse(_WEB_DIR / "app.js", media_type="text/javascript")

    @app.get("/style.css")
    async def stylesheet() -> FileResponse:
        return FileResponse(_WEB_DIR / "style.css", media_type="text/css")

    @app.post("/api/runs", status_code=202)
    async def start_run(
        request: Request,
        files: Annotated[list[UploadFile], File()],
        budget_cents: Annotated[int | None, Form()] = None,
    ) -> dict[str, Any]:
        require_local_origin(request)
        if not 1 <= len(files) <= 5:
            raise HTTPException(400, "Choose one to five CSV files")
        cap = config.budget_cents if budget_cents is None else budget_cents
        if not 1 <= cap <= 500:
            raise HTTPException(400, "Budget must be between 1 and 500 cents")
        names = [item.filename or "" for item in files]
        if any(_NAME.fullmatch(name) is None for name in names):
            raise HTTPException(400, "CSV filenames must be flat .csv names")
        labels = [Path(name).stem for name in names]
        if len({label.casefold() for label in labels}) != len(labels):
            raise HTTPException(400, "CSV names must have distinct stems")
        temp = tempfile.TemporaryDirectory(prefix="csv-analyst-")
        paths: list[Path] = []
        try:
            for uploaded, name in zip(files, names, strict=True):
                path = Path(temp.name) / name
                size = 0
                with path.open("wb") as target:
                    while chunk := await uploaded.read(65536):
                        size += len(chunk)
                        if size > _MAX_FILE:
                            raise HTTPException(413, "Each CSV must be at most 1 MB")
                        target.write(chunk)
                paths.append(path)
        except BaseException:
            temp.cleanup()
            raise
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        channel = RunChannel(run_id, labels)
        runs[run_id] = channel
        channel.launch(run_job(channel, paths, temp, cap))
        return {"run_id": run_id, "labels": labels}

    @app.get("/api/runs/{run_id}/events")
    async def events(
        run_id: str,
        last_event_id: Annotated[str | None, Header()] = None,
        after: Annotated[int | None, Query(ge=0)] = None,
    ) -> StreamingResponse:
        channel = channel_for(run_id)
        cursor = last_event_id if last_event_id is not None else str(after or 0)
        if not cursor.isdecimal() or int(cursor) >= channel.next_id:
            raise HTTPException(400, "Invalid event cursor")
        after_id = int(cursor)
        if (
            channel.events
            and after_id < channel.events[0][0] - 1
            and (last_event_id is not None or after is not None)
        ):
            raise HTTPException(409, "Replay window expired")

        async def stream() -> Any:
            queue: asyncio.Queue[tuple[int, ProgressEvent]] = asyncio.Queue(
                maxsize=1024
            )
            replay = [entry for entry in channel.events if entry[0] > after_id]
            channel.subscribers.add(queue)
            try:
                for sequence, event in replay:
                    yield f"id: {sequence}\ndata: {json.dumps(asdict(event))}\n\n"
                if channel.summary is not None and not channel.busy_sessions:
                    return
                while queue in channel.subscribers:
                    try:
                        sequence, event = await asyncio.wait_for(queue.get(), 15)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    yield f"id: {sequence}\ndata: {json.dumps(asdict(event))}\n\n"
                    if (
                        channel.summary is not None
                        and not channel.busy_sessions
                        and queue.empty()
                    ):
                        return
            finally:
                channel.subscribers.discard(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}")
    async def summary(run_id: str) -> JSONResponse:
        channel = channel_for(run_id)
        if channel.summary is None:
            if channel.failure:
                raise HTTPException(500, channel.failure)
            return JSONResponse({"status": "running"}, status_code=202)
        return JSONResponse(_redact(channel.summary.to_dict(), config.api_key))

    def artifact_path(run_id: str, label: str, name: str) -> Path:
        channel = channel_for(run_id)
        if (
            label not in channel.labels
            or not _ARTIFACT.fullmatch(name)
            or name not in channel.allowed.get(label, set())
        ):
            raise HTTPException(404, "Artifact not found")
        path = output_root / run_id / label / name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, "Artifact not found")
        return path

    @app.get("/api/runs/{run_id}/{label}/artifacts/{name}")
    async def artifact(run_id: str, label: str, name: str) -> Response:
        path = artifact_path(run_id, label, name)
        if name.endswith(".png"):
            return FileResponse(
                path,
                media_type="image/png",
                headers={"X-Content-Type-Options": "nosniff"},
            )
        content = path.read_text(encoding="utf-8", errors="replace")
        return Response(
            _redact(content, config.api_key),
            media_type="text/plain",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{name}"',
            },
        )

    @app.get("/api/runs/{run_id}/{label}/report")
    async def report(run_id: str, label: str) -> HTMLResponse:
        channel = channel_for(run_id)
        reports = [
            name
            for name in channel.allowed.get(label, set())
            if name == "report.md"
            or re.fullmatch(r"followup_[1-9][0-9]*_report\.md", name)
        ]
        if not reports:
            raise HTTPException(404, "Report not found")
        chosen = max(
            reports,
            key=lambda name: 0 if name == "report.md" else int(name.split("_", 2)[1]),
        )
        markdown = _redact(
            artifact_path(run_id, label, chosen).read_text(encoding="utf-8"),
            config.api_key,
        )
        parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
        tokens = parser.parse(markdown)
        for token in tokens:
            if token.children is None:
                continue
            for child in token.children:
                if child.type != "image":
                    continue
                source = child.attrGet("src") or ""
                if source in channel.allowed.get(label, set()) and source.endswith(
                    ".png"
                ):
                    child.attrSet(
                        "src",
                        f"/api/runs/{quote(run_id)}/{quote(label)}/artifacts/{quote(source)}",
                    )
                else:
                    child.attrSet("src", "")
        rendered = parser.renderer.render(tokens, parser.options, {})
        return HTMLResponse(
            f"<article class='report'>{rendered}</article>",
            headers={
                "Content-Security-Policy": "default-src 'none'; img-src 'self'",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/api/sessions/{session_id}/ask", status_code=202)
    async def ask(session_id: str, body: AskBody, request: Request) -> dict[str, str]:
        require_local_origin(request)
        channel = session_for(session_id)
        label = next(
            item.label
            for item in (channel.summary.sessions if channel.summary else [])
            if item.session_id == session_id
        )
        if session_id in channel.busy_sessions:
            raise HTTPException(409, "Session is already busy")
        channel.busy_sessions.add(session_id)

        async def job() -> None:
            platform: SessionPlatform | None = None
            terminal: ProgressEvent | None = None

            def on_progress(event: ProgressEvent) -> None:
                nonlocal terminal
                event = replace(event, label=label)
                if event.kind == "done":
                    terminal = event
                else:
                    safe_event(channel, event)

            try:
                platform = platform_factory()
                result, files = await ask_session(
                    platform,
                    session_id,
                    body.question,
                    timeout_s=config.timeout_s,
                    output_root=output_root,
                    sink=on_progress,
                )
                session = next(
                    item
                    for item in (channel.summary.sessions if channel.summary else [])
                    if item.session_id == session_id
                )
                session.status = result.status
                session.stop_reason = result.stop_reason
                session.list_cost_cents = result.list_cost_cents
                session.active_seconds = result.active_seconds
                channel.allowed.setdefault(session.label, set()).update(
                    path.name for path in files
                )
                if channel.summary:
                    channel.summary.save(output_root / channel.run_id)
                safe_event(
                    channel,
                    terminal
                    or ProgressEvent(
                        session_id,
                        label,
                        "done",
                        result.stop_reason,
                        stop_reason=result.stop_reason,
                    ),
                )
            except Exception as exc:
                safe_event(
                    channel,
                    ProgressEvent(
                        session_id, label, "error", f"{type(exc).__name__}: {exc}"
                    ),
                )
                safe_event(
                    channel,
                    ProgressEvent(
                        session_id, label, "done", "failed", stop_reason="error"
                    ),
                )
            finally:
                try:
                    if platform is not None:
                        await platform.close()
                finally:
                    channel.busy_sessions.discard(session_id)

        channel.launch(job())
        return {"session_id": session_id}

    @app.post("/api/sessions/{session_id}/raise-budget", status_code=202)
    async def raise_budget(
        session_id: str, body: BudgetBody, request: Request
    ) -> dict[str, str]:
        require_local_origin(request)
        channel = session_for(session_id)
        label = next(
            item.label
            for item in (channel.summary.sessions if channel.summary else [])
            if item.session_id == session_id
        )
        if session_id in channel.busy_sessions:
            raise HTTPException(409, "Session is already busy")
        channel.busy_sessions.add(session_id)

        async def job() -> None:
            platform: SessionPlatform | None = None
            terminal: ProgressEvent | None = None

            def on_progress(event: ProgressEvent) -> None:
                nonlocal terminal
                event = replace(event, label=label)
                if event.kind == "done":
                    terminal = event
                else:
                    safe_event(channel, event)

            try:
                platform = platform_factory()
                session_info = await platform.retrieve_session(session_id)
                destination = session_artifact_dir(session_info, output_root)
                result = await resume_budget_session(
                    platform,
                    session_id,
                    body.to_cents,
                    timeout_s=config.timeout_s,
                    sink=on_progress,
                )
                session = next(
                    item
                    for item in (channel.summary.sessions if channel.summary else [])
                    if item.session_id == session_id
                )
                session.status = result.status
                session.stop_reason = result.stop_reason
                session.list_cost_cents = result.list_cost_cents
                session.active_seconds = result.active_seconds
                if result.status == "completed":
                    input_name = Path(session.input_file).name
                    await collect(platform, session_id, destination, input_name)
                    session.artifacts_path = str(destination)
                    channel.allowed[session.label] = _initial_artifacts(destination)
                if channel.summary:
                    channel.summary.save(output_root / channel.run_id)
                safe_event(
                    channel,
                    terminal
                    or ProgressEvent(
                        session_id,
                        label,
                        "done",
                        result.stop_reason,
                        stop_reason=result.stop_reason,
                    ),
                )
            except Exception as exc:
                safe_event(
                    channel,
                    ProgressEvent(
                        session_id, label, "error", f"{type(exc).__name__}: {exc}"
                    ),
                )
                safe_event(
                    channel,
                    ProgressEvent(
                        session_id, label, "done", "failed", stop_reason="error"
                    ),
                )
            finally:
                try:
                    if platform is not None:
                        await platform.close()
                finally:
                    channel.busy_sessions.discard(session_id)

        channel.launch(job())
        return {"session_id": session_id}

    return app
