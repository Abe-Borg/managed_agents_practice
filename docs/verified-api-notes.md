# Verified API notes

Rule: nothing goes in code that isn't in this file or re-verified in the same PR. A row marked **from plan, re-verify** is a planning note, not a verified API contract.

## Phase 1 documentation checks

Checked the official pages on 2026-09-28 PT. The `.md` page variants returned an unsupported content type in the browsing tool, so these checks used the same pages' HTML versions. No Managed Agents API call was made.

| Fact | Value | Source URL | Verified (PT) | By (phase/PR) | Method |
|------|-------|-----------|---------------|---------------|--------|
| Managed Agents status and beta header | Beta; `managed-agents-2026-04-01` is required on every Managed Agents endpoint, and the SDK sets it automatically. | https://platform.claude.com/docs/en/managed-agents/overview | 2026-09-28 | Phase 1 / PR #1 | docs |
| Managed Agents access | Enabled by default for Claude API accounts; an API key is required. | https://platform.claude.com/docs/en/managed-agents/overview | 2026-09-28 | Phase 1 / PR #1 | docs |
| Python SDK installation and key | Quickstart shows `pip install anthropic` and `ANTHROPIC_API_KEY` as an environment variable. | https://platform.claude.com/docs/en/managed-agents/quickstart | 2026-09-28 | Phase 1 / PR #1 | docs |
| Latest Python SDK release observed | `anthropic==1.9.0`, released 2026-09-28; package metadata requires Python 3.10 or later, including the planned Python 3.12. | https://pypi.org/project/anthropic/ | 2026-09-28 | Phase 1 / PR #1 | docs |
| Planned default model | `claude-haiku-4-5` is the API alias for `claude-haiku-4-5-20251001`; current model table lists $1 input / $5 output per million tokens and no effort setting. | https://platform.claude.com/docs/en/about-claude/models/overview | 2026-09-28 | Phase 1 / PR #1 | docs |
| Default model retirement status | `claude-haiku-4-5-20251001` is active, with retirement no sooner than 2026-10-15. Recheck before any live session. | https://platform.claude.com/docs/en/about-claude/model-deprecations | 2026-09-28 | Phase 1 / PR #1 | docs |

## Plan snapshot: from plan, re-verify before implementation

The following entries seed §4 of [the implementation plan](../IMPLEMENTATION_PLAN.md). Their values have **not** been independently checked here. Re-fetch the linked official pages in the phase that uses each fact and replace the status with a dated verification before relying on it in code.

| Fact | Value from plan §4 | Source URL to check | Verified (PT) | By (phase/PR) | Method |
|------|--------------------|---------------------|---------------|---------------|--------|
| HTTP API conventions | Base `https://api.anthropic.com`; `x-api-key`, `anthropic-version: 2023-06-01`, and Managed Agents beta header; some stream examples use `?beta=true`. | https://platform.claude.com/docs/en/managed-agents/overview | — | plan §4; re-verify | plan snapshot |
| Managed Agents rate limits | Plan says 300 create requests/minute and 1,200 read requests/minute per organization, subject to other limits. | https://platform.claude.com/docs/en/managed-agents/reference | — | plan §4; re-verify | plan snapshot |
| Agent operations | `beta.agents.create/update/retrieve/list/archive` and `beta.agents.versions.list`; updates create versions. Verify exact request parameters and optimistic concurrency semantics in Phase 2. | https://platform.claude.com/docs/en/managed-agents/agent-setup | — | plan §4; re-verify | plan snapshot |
| Environment operations | `beta.environments.create/retrieve/list/archive/delete`; verify cloud networking fields and lifecycle in Phase 2. | https://platform.claude.com/docs/en/managed-agents/environments | — | plan §4; re-verify | plan snapshot |
| Agent toolset | `agent_toolset_20260401` with `default_config` and per-tool `configs`; check names and permission defaults in Phase 2. | https://platform.claude.com/docs/en/managed-agents/tools | — | plan §4; re-verify | plan snapshot |
| Session operations | `beta.sessions.create/retrieve/list/update/archive/delete`; agent reference, environment, resources, budget, and metadata shape need Phase 3 verification. | https://platform.claude.com/docs/en/managed-agents/sessions | — | plan §4; re-verify | plan snapshot |
| Session event methods | `beta.sessions.events.send/stream/list`; plan says open stream before sending; async stream behavior requires installed-SDK inspection. | https://platform.claude.com/docs/en/managed-agents/events-and-streaming | — | plan §4; re-verify | plan snapshot |
| Event taxonomy | Plan lists `user.message`, `user.interrupt`, `agent.message`, `agent.tool_use`, `agent.tool_result`, `session.status_*`, `session.usage`, `session.error`, and opt-in stream deltas; verify payload fields and terminal event ordering. | https://platform.claude.com/docs/en/managed-agents/reference | — | plan §4; re-verify | plan snapshot |
| Files in and out | `files.upload`; mounted files under `/mnt/session/uploads/`; outputs under `/mnt/session/outputs/`; `beta.files.list(scope_id=..., betas=[...])` and `files.download`. Verify method signatures, scope, and output delay. | https://platform.claude.com/docs/en/managed-agents/files | — | plan §4; re-verify | plan snapshot |
| Budget and usage | `max_list_cost.amount` is a whole-cent string in USD; plan lists `budget_reached` and `usage.list_cost` semantics. Verify before Phase 3 and again for budget updates in Phase 5. | https://platform.claude.com/docs/en/managed-agents/budgets | — | plan §4; re-verify | plan snapshot |
| Skill operations | `skills.create(files=files_from_dir(...))` and `skills.versions.create`; verify upload and agent attachment fields before Phase 4. | https://platform.claude.com/docs/en/managed-agents/skills | — | plan §4; re-verify | plan snapshot |
| Other model IDs and prices | Plan lists `claude-fable-5-1`, `claude-opus-5-5`, and `claude-sonnet-5-5`; recheck prices and model availability when selecting an override. | https://platform.claude.com/docs/en/about-claude/models/overview | — | plan §4; re-verify | plan snapshot |

## Live-call observations

None. No API key was present in the agent environment during this Phase 1 documentation review.

## SDK observations

None. SDK signatures and asynchronous streaming behavior have not been inspected locally.
