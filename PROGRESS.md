# PROGRESS: csv-analyst (Managed Agents first program)

Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · Verified notes: [docs/verified-api-notes.md](docs/verified-api-notes.md)

## Phases

| # | Phase | Status | PR | Date (PT) | Notes |
|---|-------|--------|----|-----------|-------|
| 1 | Scaffold, fixtures, tracking files | ✅ done | [#1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) | 2026-09-28 | Merged 2026-09-28 PT; offline checks passed (13 tests). |
| 2 | Environment + saved Agent (`setup`) | ✅ done | [#2](https://github.com/Abe-Borg/managed_agents_practice/pull/2) | 2026-09-28 | Merged 2026-09-28 PT; 23 offline tests passed. Live verification pending (no key in agent env). |
| 3 | First session end-to-end (file in → stream → artifacts out, budget) | ✅ done | [#3](https://github.com/Abe-Borg/managed_agents_practice/pull/3) | 2026-09-29 | Merged 2026-09-29 PT; 33 offline tests passed. Phase 3 live verification remains pending. |
| 4 | Custom Skill + agent versioning + session overrides | 🔍 in review | [#4](https://github.com/Abe-Borg/managed_agents_practice/pull/4) | 2026-09-29 | Skill lifecycle, v2 Agent, version pins, and model overrides; 48 offline tests passed after review fixes. Live verification pending (local runner unavailable; key presence unverified). |
| 5 | Parallel sessions, isolation proof, budget_reached + raise-budget | ⬜ todo | — | — | — |
| 6 | Stateful follow-ups, reconnect (`tail`), cleanup | ⬜ todo | — | — | — |
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

## Open questions
<!-- - [ ] question — where it came up — docs URL checked -->
<!-- - [x] resolved: answer — source URL/date -->
- [x] GitHub target resolved: [Abe-Borg/managed_agents_practice](https://github.com/Abe-Borg/managed_agents_practice) is connected, authentication works, and [Phase 1 PR #1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) is merged.
- [ ] Phase 2: does the API accept `limited` networking with `allowed_hosts=[]`? The [Environment docs](https://platform.claude.com/docs/en/managed-agents/environments) describe the fields but do not specify empty-list acceptance. Verify with `uv run csv-analyst setup` when a key is available; if rejected, use the plan's documented unrestricted fallback and record the result.
- [x] Phase 4: use resolved session Skill IDs and `manifest.skill_used` for the v1 comparison; report heading absence is not deterministic (plan §8, Phase 4).
- [ ] Phase 5: strengthen the isolation check; concurrently listing markers before writing can pass even with a shared filesystem (plan §5.5 and Phase 5).
- [ ] Phase 5: reject or disambiguate inputs with the same CSV stem so artifact directories do not collide (plan §5.1 and Phase 5).
- [ ] Phase 7: retain and replay run events for late SSE subscribers, including clients that connect after a short run completes (plan §8, Phase 7).
- [ ] Phase 8: resolve the completion banner timing conflict: the notice requires every phase marked done, while Phase 8 says to show it while Phase 8 remains in review (plan completion notice, Phase 8, and §9).

- [ ] Phase 4 live: confirm Skill upload/version response, resolved session Agent fields, report headings, and model override against the service when the local runner and API key are available.
- [ ] Local checkout: update `main` from origin when the desktop command runner is available; PR #4 was based on the confirmed merged `main` commit.

## Measured costs
<!-- - YYYY-MM-DD: model, file, rows, list_cost cents, active_seconds -->

## Next up
Phase 4: review [PR #4](https://github.com/Abe-Borg/managed_agents_practice/pull/4), sync the local checkout, and run the three budgeted live checks in `tests/live/test_live_skill.py` when a key is available. Phase 5 starts only after PR #4 merges.
