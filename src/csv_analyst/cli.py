"""Command line entry point."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from csv_analyst.agent_spec import build_agent_spec, build_environment_spec
from csv_analyst.config import Settings, load_settings
from csv_analyst.costs import format_cost
from csv_analyst.events import ProgressEvent
from csv_analyst.orchestrator import RunSummary, run_many
from csv_analyst.outputs import OutputError, collect
from csv_analyst.platform import (
    PlatformConflict,
    PlatformNotFound,
    PlatformValidationError,
    SdkPlatform,
    SdkSessionPlatform,
)
from csv_analyst.resources import (
    SKILL_DIR,
    ensure_agent,
    ensure_environment,
    ensure_skill,
    load_state,
)
from csv_analyst.runner import SessionResult, resume_budget_session

app = typer.Typer(help="Analyze CSV files with Claude Managed Agents.")


@app.callback()
def main() -> None:
    """Local CSV analysis commands."""


@app.command()
def doctor() -> None:
    """Check local configuration without contacting the API."""
    try:
        settings = load_settings()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        sdk_version = version("anthropic")
    except PackageNotFoundError:
        sdk_version = "not installed"

    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    typer.echo(f"Python: {python_version}")
    typer.echo(f"anthropic: {sdk_version}")
    typer.echo(f"ANTHROPIC_API_KEY set: {'yes' if settings.api_key else 'no'}")
    typer.echo(f"Model: {settings.display_model}")
    typer.echo(f"Budget: {settings.budget_cents} cents per session")


def _configured_settings() -> Settings:
    try:
        settings = load_settings()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if settings.api_key is None:
        typer.echo("ANTHROPIC_API_KEY is not set; configure .env first.", err=True)
        raise typer.Exit(code=2)
    return settings


def _configured_platform() -> tuple[SdkPlatform, Settings]:
    settings = _configured_settings()
    assert settings.api_key is not None
    return SdkPlatform(settings.api_key), settings


@app.command()
def setup() -> None:
    """Create or reuse the saved Environment and Agent."""
    platform, settings = _configured_platform()
    try:
        environment = ensure_environment(platform, build_environment_spec())
        saved_agent_id = load_state().agent_id
        try:
            saved_agent = (
                platform.retrieve_agent(saved_agent_id)
                if saved_agent_id is not None
                else None
            )
        except PlatformNotFound:
            saved_agent = None
        if saved_agent is None or saved_agent.archived:
            ensure_agent(platform, build_agent_spec(settings))
        skill = ensure_skill(platform, SKILL_DIR)
        agent = ensure_agent(
            platform, build_agent_spec(settings, skill_id=skill.resource.id)
        )
    except (PlatformConflict, PlatformValidationError, ValueError) as exc:
        typer.echo(f"Setup failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Environment: {environment.resource.id} ({environment.action})")
    if environment.detail == "unrestricted-fallback":
        typer.echo("Networking: unrestricted fallback (limited config was rejected)")
    typer.echo(
        f"Skill: {skill.resource.id} {skill.resource.latest_version_id} "
        f"({skill.action})"
    )
    agent_action = (
        f"updated → v{agent.resource.version}"
        if agent.action == "updated"
        else agent.action
    )
    typer.echo(f"Agent: {agent.resource.id} v{agent.resource.version} ({agent_action})")


@app.command()
def resources() -> None:
    """Show saved resource IDs and Agent version history."""
    try:
        state = load_state()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if state.environment_id is None or state.agent_id is None:
        typer.echo("No saved resources yet. Run `csv-analyst setup` first.", err=True)
        raise typer.Exit(code=2)

    platform, _ = _configured_platform()
    console = Console()
    console.print(f"Environment: {state.environment_id}")
    if state.environment_mode == "unrestricted-fallback":
        console.print("Networking: unrestricted fallback")
    console.print(f"Agent: {state.agent_id} v{state.agent_version}")
    if state.skill_id is not None:
        console.print(f"Skill: {state.skill_id} {state.skill_version}")
    table = Table(title="Agent versions")
    table.add_column("Version")
    table.add_column("Updated")
    for version_info in platform.list_agent_versions(state.agent_id):
        table.add_row(str(version_info.version), version_info.updated_at)
    console.print(table)


def _progress_table(status: str, latest: str, cost: int | None) -> Table:
    table = Table(title="CSV analysis", show_header=False)
    table.add_row("Status", status)
    table.add_row("Latest", latest[:300])
    table.add_row("Cost", format_cost(cost))
    return table


def _many_table(
    files: list[Path], states: dict[str, tuple[str, str, int | None]]
) -> Table:
    table = Table(title="CSV analysis")
    for heading in ("CSV", "Status", "Latest", "Cost"):
        table.add_column(heading)
    for file in files:
        status, latest, cost = states[file.stem]
        table.add_row(file.stem, status, latest[:80], format_cost(cost))
    return table


def _show_summary(console: Console, summary: RunSummary) -> None:
    table = Table(title="Run summary")
    for heading in (
        "CSV", "Session", "Status", "Stop reason", "Cost",
        "Active seconds", "Artifacts"
    ):
        table.add_column(heading)
    for item in summary.sessions:
        active = (
            f"{item.active_seconds:.1f}"
            if item.active_seconds is not None else "—"
        )
        table.add_row(
            item.label, item.session_id or "—", item.status, item.stop_reason,
            format_cost(item.list_cost_cents), active, item.artifacts_path or "—",
        )
    console.print(table)
    console.print(f"Run total: {format_cost(summary.total_list_cost_cents)}")
    isolation = Table(title="Isolation")
    isolation.add_column("CSV")
    isolation.add_column("Result")
    for item in summary.sessions:
        verdict = (
            "✅ pass" if item.isolation is True
            else "❌ fail" if item.isolation is False else "pending"
        )
        isolation.add_row(item.label, verdict)
    console.print(isolation)


@app.command()
def run(
    files: Annotated[list[Path], typer.Argument(help="CSV files to analyze.")],
    budget_cents: Annotated[
        int | None, typer.Option(help="Hard list-cost cap in cents per session.")
    ] = None,
    timeout_s: Annotated[
        int | None, typer.Option(help="Session timeout in seconds.")
    ] = None,
    max_parallel: Annotated[
        int | None, typer.Option(help="Maximum simultaneous sessions.")
    ] = None,
    record_events: Annotated[
        Path | None, typer.Option(help="Write raw events as JSONL.")
    ] = None,
    agent_version: Annotated[
        int | None, typer.Option(help="Pin a saved Agent version.")
    ] = None,
    model: Annotated[
        str | None, typer.Option(help="Override the model for these sessions.")
    ] = None,
    no_budget: Annotated[
        bool, typer.Option("--no-budget", help="Explicitly run without a cost cap.")
    ] = False,
) -> None:
    """Run one session per CSV and save independent artifacts."""
    settings = _configured_settings()
    try:
        state = load_state()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if state.agent_id is None or state.environment_id is None:
        typer.echo("Run csv-analyst setup first.", err=True)
        raise typer.Exit(code=2)
    if no_budget and budget_cents is not None:
        typer.echo("Choose either --budget-cents or --no-budget.", err=True)
        raise typer.Exit(code=2)
    cap = (
        None if no_budget
        else (budget_cents if budget_cents is not None else settings.budget_cents)
    )
    limit = timeout_s if timeout_s is not None else settings.timeout_s
    parallel = max_parallel if max_parallel is not None else settings.max_parallel
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output_root = Path("runs") / run_id
    console = Console()

    async def execute() -> RunSummary:
        assert settings.api_key is not None
        event_file = None
        if record_events is not None:
            record_events.parent.mkdir(parents=True, exist_ok=True)
            event_file = record_events.open("w", encoding="utf-8")
        states: dict[str, tuple[str, str, int | None]] = {
            file.stem: ("queued", "", None) for file in files
        }
        try:
            with Live(_many_table(files, states), console=console) as live:
                def on_progress(event: ProgressEvent) -> None:
                    previous = states[event.label]
                    cost = (
                        event.list_cost_cents
                        if event.list_cost_cents is not None else previous[2]
                    )
                    latest = (
                        f"[{event.tool_name}] {event.text}"
                        if event.tool_name else event.text
                    )
                    states[event.label] = (event.kind, latest, cost)
                    live.update(_many_table(files, states))

                def on_raw(label: str, event: dict[str, object]) -> None:
                    if event_file is not None:
                        payload: object = (
                            event if len(files) == 1
                            else {"label": label, "event": event}
                        )
                        event_file.write(json.dumps(payload, sort_keys=True) + "\n")
                        event_file.flush()

                summary = await run_many(
                    files,
                    lambda: SdkSessionPlatform(settings.api_key or ""),
                    state.agent_id or "",
                    state.environment_id or "",
                    run_id,
                    budget_cents=cap,
                    timeout_s=limit,
                    max_parallel=parallel,
                    output_root=output_root,
                    agent_version=agent_version,
                    model=model,
                    sink=on_progress,
                    raw_sink=on_raw,
                )
                for item in summary.sessions:
                    states[item.label] = (
                        item.status, item.stop_reason, item.list_cost_cents
                    )
                live.update(_many_table(files, states))
            return summary
        finally:
            if event_file is not None:
                event_file.close()

    try:
        summary = asyncio.run(execute())
    except (ValueError, OutputError) as exc:
        typer.echo(f"Run failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Run failed: {type(exc).__name__}", err=True)
        raise typer.Exit(code=1) from exc

    _show_summary(console, summary)
    console.print(f"Summary: {output_root / 'summary.json'}")
    if len(summary.sessions) == 1:
        item = summary.sessions[0]
        console.print(f"Session: {item.session_id}")
        console.print(f"Agent version: {item.agent_version}")
        console.print(f"Model: {item.model}")
        console.print(
            f"Attached Skills: {', '.join(item.skill_ids) if item.skill_ids else 'none'}"
        )
        console.print(f"Status: {item.status} ({item.stop_reason})")
        console.print(f"Cost: {format_cost(item.list_cost_cents)}")
        if item.artifacts_path is not None:
            console.print(f"Artifacts: {item.artifacts_path}")
    for item in summary.sessions:
        if item.status == "paused_budget" and item.session_id is not None:
            console.print(
                f"{item.label} paused at budget. Resume with: "
                f"uv run csv-analyst raise-budget {item.session_id} --to-cents N"
            )
        if item.error is not None:
            console.print(f"{item.label}: {item.error}")
    if any(item.isolation is False for item in summary.sessions):
        raise typer.Exit(code=2)
    if any(item.status not in {"completed", "paused_budget"} for item in summary.sessions):
        raise typer.Exit(code=1)


@app.command("raise-budget")
def raise_budget(
    session_id: Annotated[str, typer.Argument(help="Paused session ID.")],
    to_cents: Annotated[int, typer.Option(help="New hard cap in cents.")],
    timeout_s: Annotated[
        int | None, typer.Option(help="Resume timeout in seconds.")
    ] = None,
) -> None:
    """Raise a paused session's cap and collect its completed outputs."""
    settings = _configured_settings()
    console = Console()
    limit = timeout_s if timeout_s is not None else settings.timeout_s

    async def execute() -> tuple[SessionResult, Path | None]:
        assert settings.api_key is not None
        platform = SdkSessionPlatform(settings.api_key)
        try:
            session = await platform.retrieve_session(session_id)
            title = session.title or ""
            if not title.startswith("csv-analyst: "):
                raise ValueError("Session title does not identify a CSV input")
            input_name = title.removeprefix("csv-analyst: ")
            if Path(input_name).name != input_name or not input_name.endswith(".csv"):
                raise ValueError("Session title has an invalid CSV filename")
            with Live(
                _progress_table("resuming", "", session.list_cost_cents),
                console=console,
            ) as live:
                def on_progress(event: ProgressEvent) -> None:
                    live.update(
                        _progress_table(
                            event.kind, event.text, event.list_cost_cents
                        )
                    )

                result = await resume_budget_session(
                    platform, session_id, to_cents, timeout_s=limit,
                    sink=on_progress,
                )
                live.update(
                    _progress_table(
                        result.status, result.stop_reason, result.list_cost_cents
                    )
                )
            if result.status != "completed":
                return result, None
            destination = Path("runs") / f"resumed-{session_id}" / Path(input_name).stem
            collected = await collect(platform, session_id, destination, input_name)
            return result, collected.directory
        finally:
            await platform.close()

    try:
        result, artifacts = asyncio.run(execute())
    except (ValueError, OutputError) as exc:
        typer.echo(f"Raise budget failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Raise budget failed: {type(exc).__name__}", err=True)
        raise typer.Exit(code=1) from exc
    console.print(f"Session: {session_id}")
    console.print(f"Status: {result.status} ({result.stop_reason})")
    console.print(f"Cost: {format_cost(result.list_cost_cents)}")
    if artifacts is not None:
        console.print(f"Artifacts: {artifacts}")
    if result.status == "paused_budget":
        console.print(
            f"Still paused. Raise again above consumed cost: "
            f"uv run csv-analyst raise-budget {session_id} --to-cents N"
        )
    elif result.status != "completed":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
