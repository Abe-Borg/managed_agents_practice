# PROGRESS: csv-analyst (Managed Agents first program)

Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · Verified notes: [docs/verified-api-notes.md](docs/verified-api-notes.md)

## Phases

| # | Phase | Status | PR | Date (PT) | Notes |
|---|-------|--------|----|-----------|-------|
| 1 | Scaffold, fixtures, tracking files | ✅ done | [#1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) | 2026-09-28 | Merged 2026-09-28 PT; offline checks passed (13 tests). |
| 2 | Environment + saved Agent (`setup`) | 🚧 in progress | — | 2026-09-28 | API docs and SDK signatures re-verified; 22 offline tests pass. Live verification pending (no key in agent env). |
| 3 | First session end-to-end (file in → stream → artifacts out, budget) | ⬜ todo | — | — | — |
| 4 | Custom Skill + agent versioning + session overrides | ⬜ todo | — | — | — |
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

## Open questions
<!-- - [ ] question — where it came up — docs URL checked -->
<!-- - [x] resolved: answer — source URL/date -->
- [x] GitHub target resolved: [Abe-Borg/managed_agents_practice](https://github.com/Abe-Borg/managed_agents_practice) is connected, authentication works, and [Phase 1 PR #1](https://github.com/Abe-Borg/managed_agents_practice/pull/1) is open.
- [ ] Phase 2: does the API accept `limited` networking with `allowed_hosts=[]`? The [Environment docs](https://platform.claude.com/docs/en/managed-agents/environments) describe the fields but do not specify empty-list acceptance. Verify with `uv run csv-analyst setup` when a key is available; if rejected, use the plan's documented unrestricted fallback and record the result.
- [ ] Phase 4: replace the unskilled-report heading absence check with a deterministic version and skill-use check; model output alone cannot guarantee an omitted heading (plan §8, Phase 4).
- [ ] Phase 5: strengthen the isolation check; concurrently listing markers before writing can pass even with a shared filesystem (plan §5.5 and Phase 5).
- [ ] Phase 5: reject or disambiguate inputs with the same CSV stem so artifact directories do not collide (plan §5.1 and Phase 5).
- [ ] Phase 7: retain and replay run events for late SSE subscribers, including clients that connect after a short run completes (plan §8, Phase 7).
- [ ] Phase 8: resolve the completion banner timing conflict: the notice requires every phase marked done, while Phase 8 says to show it while Phase 8 remains in review (plan completion notice, Phase 8, and §9).

## Measured costs
<!-- - YYYY-MM-DD: model, file, rows, list_cost cents, active_seconds -->

## Next up
Phase 2: Environment + saved Agent (`setup`). First task: open the Phase 2 PR, then run the live setup check when an API key is available. Blockers: live acceptance requires an API key, which is absent from this environment.
