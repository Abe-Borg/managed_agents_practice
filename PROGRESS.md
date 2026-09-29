# PROGRESS: csv-analyst (Managed Agents first program)

Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · Verified notes: [docs/verified-api-notes.md](docs/verified-api-notes.md)

## Phases

| # | Phase | Status | PR | Date (PT) | Notes |
|---|-------|--------|----|-----------|-------|
| 1 | Scaffold, fixtures, tracking files | 🚧 in progress | — | 2026-09-28 | Scaffold and documentation checks complete locally; PR pending a GitHub remote and working authentication. |
| 2 | Environment + saved Agent (`setup`) | ⬜ todo | — | — | — |
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

## Open questions
<!-- - [ ] question — where it came up — docs URL checked -->
<!-- - [x] resolved: answer — source URL/date -->
- [ ] Which GitHub repository should receive the Phase 1 PR? This workspace began empty, with no remote, and GitHub CLI authentication is invalid.
- [ ] Phase 4: replace the unskilled-report heading absence check with a deterministic version and skill-use check; model output alone cannot guarantee an omitted heading (plan §8, Phase 4).
- [ ] Phase 5: strengthen the isolation check; concurrently listing markers before writing can pass even with a shared filesystem (plan §5.5 and Phase 5).
- [ ] Phase 5: reject or disambiguate inputs with the same CSV stem so artifact directories do not collide (plan §5.1 and Phase 5).
- [ ] Phase 7: retain and replay run events for late SSE subscribers, including clients that connect after a short run completes (plan §8, Phase 7).
- [ ] Phase 8: resolve the completion banner timing conflict: the notice requires every phase marked done, while Phase 8 says to show it while Phase 8 remains in review (plan completion notice, Phase 8, and §9).

## Measured costs
<!-- - YYYY-MM-DD: model, file, rows, list_cost cents, active_seconds -->

## Next up
Phase 1: Scaffold, fixtures, tracking files. First task: attach the intended GitHub remote, authenticate, and open the Phase 1 PR. Blockers: no remote and invalid GitHub CLI authentication. Phase 2 starts after Phase 1 is merged.
