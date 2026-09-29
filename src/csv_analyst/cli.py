"""Command line entry point."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import typer
from rich.console import Console
from rich.table import Table

from csv_analyst.agent_spec import build_agent_spec, build_environment_spec
from csv_analyst.config import Settings, load_settings
from csv_analyst.platform import PlatformConflict, PlatformValidationError, SdkPlatform
from csv_analyst.resources import ensure_agent, ensure_environment, load_state

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


def _configured_platform() -> tuple[SdkPlatform, Settings]:
    try:
        settings = load_settings()
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if settings.api_key is None:
        typer.echo("ANTHROPIC_API_KEY is not set; configure .env first.", err=True)
        raise typer.Exit(code=2)
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


if __name__ == "__main__":
    app()
