# PROGRESS: csv-analyst (Managed Agents first program)

Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · Verified notes: [docs/verified-api-notes.md](docs/verified-api-notes.md)

## Phases

| # | Phase | Status | PR | Date (PT) | Notes |
|---|-------|--------|----|-----------|-------|
| 1 | Scaffold, fixtures, tracking files | ✅ done | [#1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) | 2026-09-28 | Merged 2026-09-28 PT; offline checks passed (13 tests). |
| 2 | Environment + saved Agent (`setup`) | ✅ done | [#2](https://github.com/Abe-Borg/managed_agents_practice/pull/2) | 2026-09-28 | Merged 2026-09-28 PT; 23 offline tests passed. Live verification pending (no key in agent env). |
| 3 | First session end-to-end (file in → stream → artifacts out, budget) | ✅ done | [#3](https://github.com/Abe-Borg/managed_agents_practice/pull/3) | 2026-09-29 | Merged 2026-09-29 PT; 33 offline tests passed. Phase 3 live verification remains pending. |
| 4 | Custom Skill + agent versioning + session overrides | ✅ done | [#4](https://github.com/Abe-Borg/managed_agents_practice/pull/4) | 2026-09-29 | Merged 2026-09-29 10:43 PT; 48 offline tests passed. Live verification pending. |
| 5 | Parallel sessions, isolation proof, budget_reached + raise-budget | ✅ done | [#5](https://github.com/Abe-Borg/managed_agents_practice/pull/5) | 2026-09-29 | Merged 2026-09-29 11:56 PT as `5de18ed`; 57 offline tests passed. Live verification pending (no key in agent env). |
| 6 | Stateful follow-ups, reconnect (`tail`), cleanup | 🔍 in review | [#6](https://github.com/Abe-Borg/managed_agents_practice/pull/6) | 2026-09-29 | `ask`, deduplicated `tail`, guarded `cleanup`, and `sessions`; 71 offline tests passed after review fixes. Live verification pending (no key in agent env). |
| 7 | Local web UI with live SSE | ⬜ todo | — | — | — |
| 8 | Hardening, docs, demo, completion banner | ⬜ todo | — | — | — |

Legend: ⬜ todo · 🚧 in progress · 🔍 in review · ✅ done · ⛔ blocked

## Decisions log
<!-- Append-only. Format: - YYYY-MM-DD (Phase N): decision — reason — link -->
- 2026-09-28 (Phase 1): Kept `doctor` fully offline and masked API key text in diagnostics, including when a model setting contains the key — prevents accidental key display.
- 2026-09-28 (Phase 1): Read the official HTML docs where the browsing tool could not render their `.md` variants — the HTML pages carry the same Phase 1 facts; see [verified notes](docs/verified-api-notes.md).
- 2026-09-28 (Phase 1): Published the plan-only `main` branch and set it as the repository default — the newly connected repository initially contained only `phase-1-scaffold` as its default branch — [PR #1](https://github.com/Abe-Borg/managed_agents_practice/pull/1).
- 2026-09-28 (Phase 1): Pinned CI's uv installer to the published `v10.2.0` tag — the `v10` alias does not exist, and the first PR run failed while resolving the action — [setup-uv releases](https://github.com/astral-sh/setup-uv/releases).
- 2026-09-28 (Phase 2): Confirmed [Phase 1 PR #1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) merged at 2026-09-28 20:04 PT before starting Phase 2.
- 2026-09-28 (Phase 2): If the API rejects `limited` networking with no allowed hosts, retry with the plan's documented `unrestricted` fallback, record that mode in local state, and show it in CLI output. This preserves idempotence while leaving the server's empty-list behavior for a live check.
- 2026-09-28 (Phase 2): Keep the previous Environment ID in pending cleanup state until archive succeeds, so a failed archive is retried without creating another Environment — [PR #2 review](https://github.com/Abe-Borg/managed_agents_practice/pull/2#discussion_r4129296417).
- 2026-09-28 (Phase 3): Confirmed [Phase 2 PR #2](https://github.com/Abe-Borg/managed_agents_practice/pull/2) merged at 2026-09-28 20:46 PT before starting Phase 3.
- 2026-09-28 (Phase 3): Used synthetic event JSONL fixtures for offline coverage because no API key is available to record a real stream; the opt-in live test and `--record-events` command will verify real event shapes later.
- 2026-09-29 (Phase 3 review): Treat a final `end_turn` as completed even when earlier `session.error` events were retrying; retain those errors as diagnostics so recovered sessions still collect artifacts — [PR #3 review](https://github.com/Abe-Borg/managed_agents_practice/pull/3#discussion_r4129502002).
- 2026-09-29 (Phase 4): Confirmed [Phase 3 PR #3](https://github.com/Abe-Borg/managed_agents_practice/pull/3) merged at 2026-09-29 08:30 PT before starting Phase 4.
- 2026-09-29 (Phase 4): The Skills API is generally available through `client.skills`; Managed Agents session APIs still require their beta header — [verified notes](docs/verified-api-notes.md).
- 2026-09-29 (Phase 4): On a fresh setup, create the unskilled saved Agent as v1 before attaching the custom Skill as v2, so version pinning remains demonstrable even if earlier live phases were skipped.
- 2026-09-29 (Phase 4): Use the standard library for the CSV profiler to produce the required JSON without changing the locked dependency set.
- 2026-09-29 (Phase 4): Verify the unskilled v1 through the resolved session Skill list and `manifest.skill_used=false`; heading absence is model-dependent and cannot prove version pinning.
- 2026-09-29 (Phase 4): The desktop command runner failed before launch, so work started from the merged `main` commit through the repository connection and CI ran the offline checks. Local `main` sync and local live checks remain pending.
- 2026-09-29 (Phase 4 review): Replaced missing or archived Agents with an unskilled v1 baseline before Skill attachment, required `manifest.skill_used`, and rejected duplicate CSV headers; added regression coverage — [PR #4 review](https://github.com/Abe-Borg/managed_agents_practice/pull/4).
- 2026-09-29 (Phase 6): Independently confirmed [PR #5](https://github.com/Abe-Borg/managed_agents_practice/pull/5) merged at 2026-09-29 11:56 PT as `5de18ed`, then fast-forwarded the clean original local `main` to that commit before branching.
- 2026-09-29 (Phase 6): Require each follow-up to write a numbered manifest last, listing its new flat outputs. This application convention makes delayed output collection deterministic and avoids overwriting earlier artifacts; it is not a Managed Agents API field.
- 2026-09-29 (Phase 6): `--delete` checks every remote output against the local folder and requires a complete local manifest for every submitted turn; archiving remains the default. This guards against output-listing lag and incomplete follow-ups.
- 2026-09-29 (Phase 6): `tail --follow` continues across idle turns; the default exits after current history if already idle, or at the next terminal idle event if running.
- 2026-09-29 (Phase 6 review): Re-read history before an idle `tail` exits and drain its already-open stream if the terminal event is not persisted yet, so the idle transition cannot omit buffered events — [PR #6 review](https://github.com/Abe-Borg/managed_agents_practice/pull/6#discussion_r4137349660).
- 2026-09-29 (Phase 6 review): Save newly resumed artifacts in the original run folder and also recognize the older `resumed-<session_id>` folder during guarded deletion — [PR #6 review](https://github.com/Abe-Borg/managed_agents_practice/pull/6#discussion_r4137349674).
- 2026-09-29 (Phase 6 review): Treat an already deleted recorded session as an `already_removed` outcome and continue cleanup for the other sessions — [PR #6 review](https://github.com/Abe-Borg/managed_agents_practice/pull/6#discussion_r4137349683).

- 2026-09-29 (Phase 5): Confirmed [Phase 4 PR #4](https://github.com/Abe-Borg/managed_agents_practice/pull/4) merged at 2026-09-29 10:43 PT (`ae8fe1a`) before Phase 5 work.
- 2026-09-29 (Phase 5): Use one run-wide exclusive-create marker in each sandbox to avoid the pre-write marker race; reject duplicate input stems before work starts.
- 2026-09-29 (Phase 5): Follow the documented automatic resume on budget update; do not send a new message at the cap. Require a new cap greater than reported consumed cents plus one.
- 2026-09-29 (Phase 5): Desktop command and computer-use runners failed before launch. A worktree was created from ref `main`, but its checkout SHA could not be verified; original local `main` remains unverified and unsynced. The GitHub Phase 5 branch started from verified merge commit `ae8fe1a`.

## Open questions
<!-- - [ ] question — where it came up — docs URL checked -->
<!-- - [x] resolved: answer — source URL/date -->
- [x] GitHub target resolved: [Abe-Borg/managed_agents_practice](https://github.com/Abe-Borg/managed_agents_practice) is connected, authentication works, and [Phase 1 PR #1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) is merged.
- [ ] Phase 2: does the API accept `limited` networking with `allowed_hosts=[]`? The [Environment docs](https://platform.claude.com/docs/en/managed-agents/environments) describe the fields but do not specify empty-list acceptance. Verify with `uv run csv-analyst setup` when a key is available; if rejected, use the plan's documented unrestricted fallback and record the result.
- [x] Phase 4: use resolved session Skill IDs and `manifest.skill_used` for the v1 comparison; report heading absence is not deterministic (plan §8, Phase 4).
- [x] Phase 5: add a run-wide exclusive-create marker; in a shared filesystem only one session could create it, regardless of timing (plan §5.5 and Phase 5).
- [x] Phase 5: reject case-insensitive duplicate CSV stems before creating sessions (plan §5.1 and Phase 5).
- [ ] Phase 7: retain and replay run events for late SSE subscribers, including clients that connect after a short run completes (plan §8, Phase 7).
- [ ] Phase 8: resolve the completion banner timing conflict: the notice requires every phase marked done, while Phase 8 says to show it while Phase 8 remains in review (plan completion notice, Phase 8, and §9).

- [ ] Phase 4 live: confirm Skill upload/version response, resolved session Agent fields, report headings, and model override against the service when the local runner and API key are available.
- [ ] Phase 5 live: confirm three overlapping sessions with isolation passes, then a 5-cent budget pause and 100-cent resume; record measured costs.
- [x] Local checkout: original `main` was fast-forwarded from `4190f63` to verified Phase 5 merge `5de18ed` on 2026-09-29 PT.
- [ ] Phase 6 live: confirm a follow-up actually reads the checkpointed `analysis.py`, numbered artifacts appear, `tail` returns complete history, and default cleanup archives sessions.

## Phase 5 live commands (pending)

With a locally configured API key:

```powershell
uv run csv-analyst setup
uv run csv-analyst run fixtures/sales.csv fixtures/weather.csv fixtures/web_traffic.csv --max-parallel 3
uv run csv-analyst run fixtures/sales.csv --budget-cents 5
uv run csv-analyst raise-budget <session_id_from_previous_command> --to-cents 100
```

The opt-in automated checks are `$env:CSV_ANALYST_LIVE = '1'` followed by `uv run pytest -m live tests/live/test_live_parallel.py -s`. They create four additional budgeted sessions.

## Pending Phase 2–6 live acceptance (no key in agent env)

Run from the repository root with `ANTHROPIC_API_KEY` configured in the local environment or ignored `.env`; do not put it in a command or commit it. Each `run` uses a session budget. Record `list_cost_cents` and `active_seconds` from the CLI or `runs/<run_id>/summary.json` under Measured costs.

```powershell
# Phase 2: second setup must report unchanged; resources shows Agent versions.
uv run csv-analyst setup
uv run csv-analyst setup
uv run csv-analyst resources

# Phase 3: inspect runs/<run_id>/tiny/ and the recorded event stream.
uv run csv-analyst run fixtures/tiny.csv --budget-cents 50 --record-events runs/tiny-events.jsonl

# Phase 4: compare resolved Agent version/Skill use and model override.
uv run csv-analyst run fixtures/tiny.csv --agent-version 1 --budget-cents 50
uv run csv-analyst run fixtures/tiny.csv --model claude-sonnet-5-5 --budget-cents 50
uv run csv-analyst resources

# Phase 5: record the sales session and run IDs printed by the parallel run.
uv run csv-analyst run fixtures/sales.csv fixtures/weather.csv fixtures/web_traffic.csv --max-parallel 3
uv run csv-analyst run fixtures/sales.csv --budget-cents 5
uv run csv-analyst raise-budget <paused_session_id> --to-cents 100

# Phase 6: use the sales session and run IDs from the parallel run.
uv run csv-analyst ask <sales_session_id> "Break revenue down by region with one chart"
uv run csv-analyst tail <sales_session_id>
uv run csv-analyst cleanup --run <parallel_run_id>
```

The separate opt-in automated Phase 6 check is `$env:CSV_ANALYST_LIVE = '1'; uv run pytest -m live tests/live/test_live_followup.py -s`. It creates one additional session capped at 100 cents and archives it after the checks.

## Measured costs
<!-- - YYYY-MM-DD: model, file, rows, list_cost cents, active_seconds -->

## Next up
Phase 6: review [PR #6](https://github.com/Abe-Borg/managed_agents_practice/pull/6) and run the pending Phase 2–6 live acceptance when an API key is available locally. Phase 7 starts only after PR #6 merges.
