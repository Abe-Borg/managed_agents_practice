# Architecture

`csv-analyst` has a local CLI (`src/csv_analyst/cli.py`) and a loopback-only FastAPI UI (`src/csv_analyst/web/app.py`). Both use the same run orchestration. `src/csv_analyst/platform.py` is the only boundary that calls the Anthropic SDK; the browser never receives the API key or remote file IDs.

## Data flow for one run

```text
CLI run / browser POST /api/runs
    │
    ▼
orchestrator.run_many ── semaphore(max_parallel) ── one task per CSV
    │                                             │
    │                                    runner.run_session
    │                                      1. files.upload(csv)
    │                                      2. sessions.create(saved Agent or
    │                                         pinned version / model override,
    │                                         Environment, file mount, budget)
    │                                      3. open events.stream before send
    │                                      4. send user.message from prompts.py
    │                                      5. normalize events → CLI table or
    │                                         web RunChannel → browser SSE
    │                                      6. stop at idle / termination / timeout
    │                                             │
    │                                    outputs.collect polls session-scoped
    │                                    Files API until manifest appears
    │                                             │
    └── isolation check over manifests ← report.md, chart_*.png,
        and summary.json                 analysis.py, manifest.json
```

`setup` uses `resources.ensure_environment`, `ensure_skill`, and `ensure_agent` to save reusable IDs in gitignored local state. `agent_spec.py` defines the restricted toolset and Environment configuration. One CSV is uploaded and mounted read-only at `/mnt/session/uploads/<name>.csv` in each session. `prompts.py` asks the agent to write flat outputs under `/mnt/session/outputs/` and records the isolation probe in `manifest.json`. `outputs.collect` lists files with the session ID as `scope_id`, waits for the manifest, validates it, and downloads only expected files. `orchestrator.check_isolation` verifies the uploaded filename and exclusive run marker before writing `runs/<run_id>/summary.json`.

The CLI renders normalized `ProgressEvent`s from `events.py`. The web server relays the same events through a `RunChannel`, assigns local SSE sequence IDs, and retains the newest 10,000 per run for late subscribers. This replay is in process and disappears on restart. The web route serves only locally collected, manifest-listed artifacts; reports are escaped before chart links are rewritten. The key remains in the server process.

`runner.ask_session` sends a later `user.message` to an idle session, reusing its checkpointed sandbox and saving `followup_<n>_*` outputs. `runner.resume_budget_session` updates an existing cap and consumes the automatically resumed turn. `runner.tail_session` opens a stream before listing history and skips duplicate event IDs. `runner.cleanup_run` archives owned idle sessions by default, and checks local output completeness before deletion. A cancelled CLI turn sends `user.interrupt` to its remote session.

## Boundaries and limits

- The default per-session cap is 100 whole USD cents. A cap is enforced between model requests; `list_cost` is rounded and can exceed the cap after an in-flight request. Runtime billing accrues only while `running`. See [budgets](https://platform.claude.com/docs/en/managed-agents/budgets) and [pricing](https://platform.claude.com/docs/en/about-claude/pricing).
- The platform keeps sandbox files for 30 days from sandbox creation. Follow-ups after that window must use a new run. See [event streaming and resume](https://platform.claude.com/docs/en/managed-agents/events-and-streaming).
- The app has local-only UI access and no user accounts. Its SSE replay and `runs/` files are local application state, separate from the platform's persisted session history.
