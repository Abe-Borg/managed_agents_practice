"""Command line entry point."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import typer

from csv_analyst.config import load_settings

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


if __name__ == "__main__":
    app()
