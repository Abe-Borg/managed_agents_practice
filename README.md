# csv-analyst

`csv-analyst` is a planned local CLI and web app for analyzing CSV files with Claude Managed Agents. Each CSV will run in its own managed session and produce a report, charts, and downloadable analysis files. The current Phase 1 scaffold provides project configuration, sample CSVs, and an offline health check; agent sessions and the web UI arrive in later phases.

## Get started

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run these commands from the repository root:

```powershell
uv sync
Copy-Item .env.example .env
uv run csv-analyst doctor
```

Edit `.env` to change the model or budget. An Anthropic API key is not needed for `doctor`. When you later run commands that use Managed Agents, set `ANTHROPIC_API_KEY` in your environment or in the local `.env` file. Keep that file private; `.env.example` contains placeholder values only.

`doctor` reports the Python and `anthropic` SDK versions, whether a key is present, the selected model, and the budget. It does not make an API request or display the key.

## Check the scaffold

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -m "not live"
```

See [PROGRESS.md](PROGRESS.md) for phase status and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the planned features.
