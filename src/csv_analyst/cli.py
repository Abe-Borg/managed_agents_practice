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
from csv_analyst.outputs import OutputError, collect
from csv_analyst.platform import (
    PlatformConflict,
    PlatformValidationError,
    SdkPlatform,
    SdkSessionPlatform,
)
from csv_analyst.resources import ensure_agent, ensure_environment, load_state
from csv_analyst.runner import SessionResult, run_session

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
        agent = ensure_agent(platform, build_agent_spec(settings))
    except (PlatformConflict, PlatformValidationError, ValueError) as exc:
        typer.echo(f"Setup failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Environment: {environment.resource.id} ({environment.action})")
    if environment.detail == "unrestricted-fallback":
        typer.echo("Networking: unrestricted fallback (limited config was rejected)")
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


@app.command()
def run(
    file: Annotated[Path, typer.Argument(help="One CSV file to analyze.")],
    budget_cents: Annotated[
        int | None, typer.Option(help="Hard list-cost cap in cents.")
    ] = None,
    timeout_s: Annotated[
        int | None, typer.Option(help="Session timeout in seconds.")
    ] = None,
    record_events: Annotated[
        Path | None, typer.Option(help="Write raw events as JSONL.")
    ] = None,
    no_budget: Annotated[
        bool, typer.Option("--no-budget", help="Explicitly run without a cost cap.")
    ] = False,
) -> None:
    """Run one CSV through a Managed Agents session and save its artifacts."""
    settings = _configured_settings()
    try:
        state = load_state()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if state.agent_id is None or state.environment_id is None:
        typer.echo("Run `csv-analyst setup` first.", err=True)
        raise typer.Exit(code=2)
    agent_id = state.agent_id
    environment_id = state.environment_id
    if no_budget and budget_cents is not None:
        typer.echo("Choose either --budget-cents or --no-budget.", err=True)
        raise typer.Exit(code=2)
    cap = (
        None
        if no_budget
        else (budget_cents if budget_cents is not None else settings.budget_cents)
    )
    limit = timeout_s if timeout_s is not None else settings.timeout_s
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    destination = Path("runs") / run_id / file.stem
    console = Console()

    async def execute() -> tuple[SessionResult, Path | None]:
        assert settings.api_key is not None
        platform = SdkSessionPlatform(settings.api_key)
        event_file = None
        if record_events is not None:
            record_events.parent.mkdir(parents=True, exist_ok=True)
            event_file = record_events.open("w", encoding="utf-8")
        try:
            with Live(
                _progress_table("starting", "Uploading CSV", None), console=console
            ) as live:
                current_cost: int | None = None

                def on_progress(event: ProgressEvent) -> None:
                    nonlocal current_cost
                    if event.list_cost_cents is not None:
                        current_cost = event.list_cost_cents
                    live.update(_progress_table(event.kind, event.text, current_cost))
                    if event.kind in {"tool_use", "message", "error"}:
                        label = f"[{event.tool_name}] " if event.tool_name else ""
                        console.print(f"{label}{event.text}", markup=False)

                def on_raw(event: dict[str, object]) -> None:
                    if event_file is not None:
                        event_file.write(json.dumps(event, sort_keys=True) + "\n")
                        event_file.flush()

                result = await run_session(
                    platform,
                    file,
                    agent_id,
                    environment_id,
                    run_id,
                    budget_cents=cap,
                    timeout_s=limit,
                    sink=on_progress,
                    raw_sink=on_raw,
                )
                live.update(
                    _progress_table(
                        result.status, result.stop_reason, result.list_cost_cents
                    )
                )
            if result.status != "completed":
                return result, None
            collected = await collect(
                platform, result.session_id, destination, file.name
            )
            for ignored in collected.ignored:
                console.print(f"Ignored unexpected file: {ignored}")
            return result, collected.directory
        finally:
            if event_file is not None:
                event_file.close()
            await platform.close()

    try:
        result, artifact_dir = asyncio.run(execute())
    except (ValueError, OutputError) as exc:
        typer.echo(f"Run failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Run failed: {type(exc).__name__}", err=True)
        raise typer.Exit(code=1) from exc

    console.print(f"Session: {result.session_id}")
    console.print(f"Status: {result.status} ({result.stop_reason})")
    console.print(f"Cost: {format_cost(result.list_cost_cents)}")
    if artifact_dir is not None:
        console.print(f"Artifacts: {artifact_dir}")
    else:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
