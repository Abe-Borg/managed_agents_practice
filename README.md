# csv-analyst

`csv-analyst` is a local CLI for analyzing CSV files with Claude Managed Agents. It streams managed sessions' progress and downloads reports, charts, scripts, and manifests. A local web UI is planned for a later phase.

## Get started

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run these commands from the repository root:

```powershell
uv sync
Copy-Item .env.example .env
uv run csv-analyst doctor
```

Edit `.env` to change the model or budget. An Anthropic API key is not needed for `doctor`. When you later run commands that use Managed Agents, set `ANTHROPIC_API_KEY` in your environment or in the local `.env` file. Keep that file private; `.env.example` contains placeholder values only.

`doctor` reports the Python and `anthropic` SDK versions, whether a key is present, the selected model, and the budget. It does not make an API request or display the key.

## Create saved resources

With `ANTHROPIC_API_KEY` configured locally, create the reusable Environment, custom CSV report Skill, and Agent:

```powershell
uv run csv-analyst setup
uv run csv-analyst setup       # reports unchanged on the second run
uv run csv-analyst resources   # shows Skill ID and Agent versions
```

On a fresh setup, the unskilled Agent is version 1 and attaching the Skill updates it to version 2. The Skill lives in `skills/csv-report/` and its profiling script prints a JSON summary before the report is written. The Environment starts with limited networking and no allowed outbound hosts. If the API rejects an empty host list, `setup` reports and records its unrestricted fallback.

## Analyze one CSV

After `setup`, run the small sample with a 50-cent session cap:

```powershell
uv run csv-analyst run fixtures/tiny.csv --budget-cents 50
```

To compare saved and per-session configuration, use:

```powershell
uv run csv-analyst run fixtures/tiny.csv --agent-version 1 --budget-cents 50
uv run csv-analyst run fixtures/tiny.csv --model claude-sonnet-5-5 --budget-cents 50
uv run csv-analyst run fixtures/tiny.csv --agent-version 1 --model claude-sonnet-5-5 --budget-cents 50
```

The CLI prints the resolved Agent version, model, and attached Skill IDs. The model override applies to that session and does not create an Agent version. The two options can be combined; the override then uses the pinned version as its base. The manifest records `skill_used` after the profiling script runs.

The command shows session progress, tool calls, and cumulative list cost. On a completed run it downloads `report.md`, `analysis.py`, `manifest.json`, and one or more `chart_*.png` files under `runs/<run_id>/tiny/`. `runs/` is gitignored. Use `--record-events <path>` to keep raw event JSONL locally for debugging. `--timeout-s` changes the 600-second session timeout. `--no-budget` is available only as an explicit CLI option.

The CLI accepts a single existing `.csv` file with a filename made of letters, digits, dots, underscores, or dashes. The default budget is 100 cents per session. A budget pause or other incomplete run prints the session ID and stops without claiming artifacts are complete.

To run the live smoke test explicitly, set `CSV_ANALYST_LIVE=1` and run `uv run pytest -m live tests/live/test_live_run.py`. It creates at most one 25-cent session. The Phase 4 live check uses `tests/live/test_live_skill.py` and starts three sessions capped at 50 cents each. A working API key is required; the offline test suite does not contact the service.

## Run CSVs in parallel

```powershell
uv run csv-analyst run fixtures/sales.csv fixtures/weather.csv fixtures/web_traffic.csv --max-parallel 3
```

Each CSV gets its own session, budget, artifact folder, and row in `runs/<run_id>/summary.json`. The terminal shows live status and cost for each session plus an isolation table. Inputs with the same stem are rejected before any API call.

To exercise the budget pause and automatic resume:

```powershell
uv run csv-analyst run fixtures/sales.csv --budget-cents 5
uv run csv-analyst raise-budget <session_id> --to-cents 100
```

Use the session ID printed by the first command. The new cap must exceed the session's consumed list cost by more than one cent. Raising it resumes the paused work without another message. The second command downloads completed artifacts into the original `runs/<run_id>/sales/` folder. Cleanup also recognizes the older `runs/resumed-<session_id>/sales/` location for sessions resumed before this change.

## Continue and manage sessions

```powershell
uv run csv-analyst sessions --limit 20
uv run csv-analyst ask <session_id> "Break revenue down by region with one chart"
uv run csv-analyst tail <session_id>
uv run csv-analyst cleanup --run <run_id>
```

`ask` requires an idle session and reuses its checkpointed sandbox. It saves new `followup_<n>_*` files in the original `runs/<run_id>/<stem>/` folder. `tail` prints persisted history, skips duplicate events from the live stream, and exits when an idle turn finishes. Add `--follow` to wait across idle turns. `cleanup` archives the run's owned sessions by default. `cleanup --run <run_id> --delete` permanently removes a session only after verifying its downloaded outputs locally; running sessions must first be interrupted and allowed to become idle.

## Check the scaffold

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -m "not live"
```

See [PROGRESS.md](PROGRESS.md) for phase status and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the planned features.
