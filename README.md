# csv-analyst

`csv-analyst` is a local CLI and loopback-only web UI for analyzing CSV files with [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview). It streams separate, budgeted sessions and downloads reports, charts, scripts, and manifests. See the [architecture](docs/architecture.md) and [Managed Agents benefits](docs/why-managed-agents.md).

## Get started

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/). A Claude API account with Managed Agents access is required for live commands. Then run from the repository root:

```powershell
uv sync
Copy-Item .env.example .env
uv run csv-analyst doctor
```

Edit `.env` to add `ANTHROPIC_API_KEY` locally and optionally change the model or budget. A key is not needed for `doctor`. Keep `.env` private and gitignored; `.env.example` contains placeholders only. The key stays server-side and is never sent to the browser.

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

The opt-in full live acceptance command is `CSV_ANALYST_LIVE=1 uv run pytest -m live -s`; it creates at most four budgeted sessions and covers the earlier CLI phases. The historical per-phase tests under `tests/live/` are marked `live_extra` and require `CSV_ANALYST_LIVE_EXTRA=1`; running them creates additional sessions. A working local API key is required. The offline test suite does not contact the service.

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

`ask` requires an idle session and reuses its checkpointed sandbox. It saves new `followup_<n>_*` files in the original `runs/<run_id>/<stem>/` folder. Sandbox files expire 30 days after sandbox creation, even if the session was active later; start a new run after that window. `tail` prints persisted history, skips duplicate events from the live stream, and exits when an idle turn finishes. Add `--follow` to wait across idle turns. `cleanup` archives the run's owned sessions by default. `cleanup --run <run_id> --delete` permanently removes a session only after verifying its downloaded outputs locally; running sessions must first be interrupted and allowed to become idle. Ctrl-C on an active CLI turn sends `user.interrupt` before exit.

## Web UI

```bash
uv run csv-analyst serve --port 8765
```

Open `http://127.0.0.1:8765`. Select up to five flat `.csv` files (at most 1 MB each) and watch per-session live panels. Completed reports and charts, idle-session follow-ups, and budget increases are available there. The server binds to `127.0.0.1` and keeps the API key server-side. Browser SSE replay retains the newest 10,000 normalized events per run in memory; restarting the server clears that window. This UI is for local use without user accounts.

## Demo

Run `bash scripts/demo.sh` for a guided, command-driven walkthrough with pauses. The five-minute path is:

1. Run `setup` twice and `resources` to see the saved Environment, Skill, and Agent versions.
2. Run `sales.csv`, `weather.csv`, and `web_traffic.csv` with `--max-parallel 3 --budget-cents 100`. Watch the live rows and isolation table, then open `runs/<run_id>/sales/report.md` and its charts.
3. Ask the sales session for a regional breakdown and inspect numbered follow-up artifacts from the same sandbox.
4. Run sales again with `--budget-cents 5`. If it pauses at `budget_reached`, run `raise-budget <session_id> --to-cents 100` to resume. The cap is checked between model requests, so the reported cost may slightly exceed five cents.
5. Start `serve`, upload the three fixtures at a 100-cent cap, inspect panels and reports, then use `tail <session_id>` or the Console's **Managed Agents → Sessions** viewer. Archive a run with `cleanup --run <run_id>`.

The CLI walkthrough creates four sessions. Running the web UI with three fixtures creates three more, each with its own cap; skip already-observed steps to keep live spend small.

## Cost and troubleshooting

The default model is `claude-haiku-4-5`, with a hard 100-cent list-price budget per session. `--budget-cents N` takes a positive whole number of USD cents; only the CLI offers the explicit `--no-budget` escape hatch. Usage and `runs/<run_id>/summary.json` show rounded cumulative list cost and active seconds. Current documented Managed Agents pricing is model tokens plus **$0.08 per running session-hour**, with no runtime charge while idle. Check [pricing](https://platform.claude.com/docs/en/about-claude/pricing) and [model status](https://platform.claude.com/docs/en/about-claude/model-deprecations) before a live demo. The ≤$3 full-demo target remains unmeasured until live acceptance.

| Symptom | Action |
|---|---|
| Missing key or HTTP 401 | Set `ANTHROPIC_API_KEY` in the environment or ignored `.env`, then run `doctor`. Never paste or commit it. |
| Archived or missing Agent | Re-run `setup` to create a usable Agent. |
| HTTP 400 budget error | Use whole cents such as `--budget-cents 50`; on resume, set a cap more than one cent above reported consumption. |
| HTTP 409 during setup | Setup re-reads and retries once; re-run `setup` if another writer changed the Agent again. |
| HTTP 429 | Respect `Retry-After`. With no such header, check the account spend cap before retrying; the SDK's backoff is bounded to one retry. |
| `budget_reached` | Use `raise-budget <session_id> --to-cents N`; the existing turn resumes without a new message. |
| Outputs missing just after idle | Wait a few seconds and retry collection or re-list the session files; output listing can lag. |
| Old follow-up session | Sandbox state expires 30 days after creation. Start a new run for a fresh `analysis.py`. |

## Checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -m "not live"
bash -n scripts/demo.sh
```

The opt-in full live suite is `CSV_ANALYST_LIVE=1 uv run pytest -m live -s` and creates at most four sessions. See [PROGRESS.md](PROGRESS.md) for live acceptance status and measured costs.

## Next ideas

Outside this plan: outcome/rubric grading via `user.define_outcome`, the pre-built `xlsx` Skill, event deltas for token streaming, a scheduled nightly deployment, webhooks, `ant apply` resource-as-code, and limited-networking allowlists for real APIs.
