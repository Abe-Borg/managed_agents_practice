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

## Phase 2 documentation checks

Checked the official HTML pages on 2026-09-28 PT before implementing Phase 2. The installed `anthropic==1.9.0` SDK method signatures were also inspected locally. No live API call was made.

| Fact | Value | Source URL | Verified (PT) | By (phase/PR) | Method |
|------|-------|-----------|---------------|---------------|--------|
| Agent create and fields | A saved Agent has required `name` and `model`; `system`, `tools`, and `metadata` are supported. Its response includes `id`, `version`, and `archived_at`. | https://platform.claude.com/docs/en/managed-agents/agent-setup | 2026-09-28 | Phase 2 / PR #2 | docs |
| Agent update and version history | `agents.update(agent_id, version=...)` uses optional optimistic concurrency; a stale version returns 409, omitted fields are preserved, and a no-op update does not create a version. `agents.versions.list(agent_id)` is paginated. | https://platform.claude.com/docs/en/managed-agents/agent-setup | 2026-09-28 | Phase 2 / PR #2 | docs |
| Environment lifecycle | `environments.create(name=..., config=...)`, `retrieve(id)`, and `archive(id)` are documented. Environments are not versioned; archiving makes them read-only while existing sessions continue. | https://platform.claude.com/docs/en/managed-agents/environments | 2026-09-28 | Phase 2 / PR #2 | docs |
| Cloud networking | `config.type=cloud`; `networking.type=limited` uses `allowed_hosts`, `allow_mcp_servers`, and `allow_package_managers`. The latter two default to false. The docs do not say whether `allowed_hosts=[]` is accepted. | https://platform.claude.com/docs/en/managed-agents/environments | 2026-09-28 | Phase 2 / PR #2 | docs |
| Restricted built-in toolset | `agent_toolset_20260401` accepts `default_config.enabled=false` and per-tool `configs` with `name` and `enabled`; entries may omit `type` in requests. | https://platform.claude.com/docs/en/managed-agents/tools | 2026-09-28 | Phase 2 / PR #2 | docs |
| Tool permission default | The Agent toolset defaults to `always_allow`; disabled tools are removed from use rather than governed by a permission policy. | https://platform.claude.com/docs/en/managed-agents/permission-policies | 2026-09-28 | Phase 2 / PR #2 | docs |

## Phase 3 documentation checks

Checked the official HTML pages on 2026-09-28 PT before implementing Phase 3 and inspected the installed `anthropic==1.9.0` async SDK. No live API call was made.

| Fact | Value | Source URL | Verified (PT) | By (phase/PR) | Method |
|------|-------|-----------|---------------|---------------|--------|
| Session creation | A session references an Agent and Environment; create without `initial_events` then send a `user.message`. Creation accepts file `resources`, `budget`, `title`, and `metadata`. | https://platform.claude.com/docs/en/managed-agents/sessions | 2026-09-28 | Phase 3 / PR #3 | docs + SDK |
| Budget and cost | `budget.type=limit`, `max_list_cost.amount` is a whole-cent USD string; the cap is checked between model requests. `session.usage.usage.list_cost.amount` gives cumulative cents immediately before idle. | https://platform.claude.com/docs/en/managed-agents/budgets | 2026-09-28 | Phase 3 / PR #3 | docs + SDK |
| File mount and output | `files.upload(file=Path(...))`; a resource with `mount_path=/name.csv` appears at `/mnt/session/uploads/name.csv`. Output files under `/mnt/session/outputs/` may appear shortly after idle; list with `beta.files.list(scope_id=session_id, betas=["managed-agents-2026-04-01"])`, then `files.download(id)`. | https://platform.claude.com/docs/en/managed-agents/files | 2026-09-28 | Phase 3 / PR #3 | docs + SDK |
| Streaming order and terminal status | The official example opens `events.stream(session_id)` before `events.send(...)`. `session.status_idle.stop_reason.type` includes `end_turn`, `budget_reached`, `retries_exhausted`, and `requires_action`; usage is emitted before idle. `session.status_terminated` and `session.error` exist in SDK event types. | https://platform.claude.com/docs/en/managed-agents/events-and-streaming | 2026-09-28 | Phase 3 / PR #3 | docs + SDK |
| Async stream usage | Installed `AsyncEvents.stream` is an `async def` returning `AsyncStream`; await it, then use `async with stream` and `async for event in stream`. The SDK stream path includes `?beta=true` and sets the Managed Agents beta header. | https://platform.claude.com/docs/en/api/beta/sessions/events/stream | 2026-09-28 | Phase 3 / PR #3 | SDK source |
| Retry errors and final turn status | A `session.error` has `error.retry_status`; `retrying` means the server retries automatically, while `exhausted` ends the turn and `terminal` terminates the session. `session.status_idle` with `stop_reason.type=end_turn` means the agent completed its turn naturally. A prior retrying error does not override that final outcome. | https://platform.claude.com/docs/en/api/cli/beta/sessions/events | 2026-09-29 | Phase 3 / PR #3 review | docs |

## Phase 4 documentation checks

Checked the official HTML pages on 2026-09-29 PT before implementing Phase 4. No live API call was made. The Skills API is generally available through `client.skills`; Managed Agents endpoints still require their beta header.

| Fact | Value | Source URL | Verified (PT) | By (phase/PR) | Method |
|------|-------|-----------|---------------|---------------|--------|
| Custom Skill upload | A Skill bundle has `SKILL.md` at its root, optional scripts, and may be passed as `client.skills.create(files=files_from_dir(path))`. The returned Skill has `id` and `latest_version_id`. | https://platform.claude.com/docs/en/build-with-claude/skills-guide | 2026-09-29 | Phase 4 | docs |
| Skill versions | `client.skills.versions.create(skill_id=..., files=files_from_dir(path))` uploads a complete new snapshot; omitted files are not carried forward. Custom version IDs use `skver_...`. | https://platform.claude.com/docs/en/build-with-claude/skills-guide | 2026-09-29 | Phase 4 | docs |
| Skill frontmatter | `name` and `description` are required. Names are at most 64 lowercase letters, digits, or hyphens and exclude reserved words `anthropic` and `claude`; descriptions are non-empty and at most 1024 characters, with no XML tags. | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview | 2026-09-29 | Phase 4 | docs |
| Agent Skill attachment | An attached custom Skill uses `{"type":"custom","skill_id":"skill_*","version":"latest"}` in the Agent `skills` array; `version` may instead pin an exact version. | https://platform.claude.com/docs/en/managed-agents/skills | 2026-09-29 | Phase 4 | docs |
| Session agent reference and overrides | A string Agent ID selects latest; `{"type":"agent","id":...,"version":N}` pins a version. `agent_with_overrides` accepts an optional base version and replacement fields such as `model:{"id":...}`; overrides do not change the saved Agent. The response's resolved `agent` includes its ID, version, model, and effective fields. | https://platform.claude.com/docs/en/managed-agents/sessions | 2026-09-29 | Phase 4 | docs |
| Override model | `claude-sonnet-5-5` is a current Claude API model ID at $2 input and $10 output per million tokens. | https://platform.claude.com/docs/en/models/overview | 2026-09-29 | Phase 4 | docs |

## Phase 5 documentation checks

Checked official HTML documentation on 2026-09-29 PT before implementing Phase 5. No live API call was made.

| Fact | Value | Source URL | Verified (PT) | By (phase/PR) | Method |
|------|-------|-----------|---------------|---------------|--------|
| Budget pause and usage | A cap is checked between model requests and may overshoot by one in-flight request. The session emits thread idle, then cumulative session.usage (whole-cent list_cost and active_seconds), then session.status_idle with stop_reason=budget_reached. Use the session-level stop reason. | https://platform.claude.com/docs/en/managed-agents/budgets | 2026-09-29 | Phase 5 | docs |
| Events at the cap | A user.message is rejected with 400 while at/over budget. A paused session retains its history and sandbox. | https://platform.claude.com/docs/en/managed-agents/events-and-streaming | 2026-09-29 | Phase 5 | docs |
| Budget update | sessions.update(session_id, budget={"type":"limit","max_list_cost":{"amount":"500","currency":"USD"}}) automatically resumes paused work. The new cap must exceed consumed list cost; use at least one cent of margin over the reported rounded figure. A budget cannot be added to an unbudgeted session. | https://platform.claude.com/docs/en/managed-agents/budgets | 2026-09-29 | Phase 5 | docs |
| Session usage | A retrieved session carries usage.list_cost and usage.active_seconds; usage is cumulative. | https://platform.claude.com/docs/en/managed-agents/budgets | 2026-09-29 | Phase 5 | docs |
| Session update semantics | Changing an existing cap or removing it automatically resumes budget-paused work. | https://platform.claude.com/docs/en/managed-agents/session-operations | 2026-09-29 | Phase 5 | docs |
| Rate limits | Managed Agents create endpoints: 300/minute; read endpoints: 1,200/minute per organization, plus organization spending and tier limits. | https://platform.claude.com/docs/en/managed-agents/reference | 2026-09-29 | Phase 5 | docs |
| Cloud sandbox isolation | Sessions may share one Environment config, but each gets its own fresh isolated Linux container. | https://platform.claude.com/docs/en/managed-agents/environments | 2026-09-29 | Phase 5 | docs |

The plan's pre-write marker list can miss a shared filesystem when sessions check before any marker is written. Phase 5 adds an exclusive-create marker path shared by every session in a run; in a shared filesystem only one session can create it, even if checks are sequential. The manifest records the result. The CLI applies the plan's stricter budget rule (new cap > reported consumed cents + 1) to leave room for rounding and resumed work.

## Plan snapshot: remaining facts to re-verify before implementation

The following entries seed §4 of [the implementation plan](../IMPLEMENTATION_PLAN.md). Their values have **not** been independently checked here. Re-fetch the linked official pages in the phase that uses each fact and replace the status with a dated verification before relying on it in code.

| Fact | Value from plan §4 | Source URL to check | Verified (PT) | By (phase/PR) | Method |
|------|--------------------|---------------------|---------------|---------------|--------|
| HTTP API conventions | Base `https://api.anthropic.com`; `x-api-key`, `anthropic-version: 2023-06-01`, and Managed Agents beta header; some stream examples use `?beta=true`. | https://platform.claude.com/docs/en/managed-agents/overview | — | plan §4; re-verify | plan snapshot |

## Live-call observations

None. No API key was present in the agent environment during the Phase 1 or Phase 2 documentation review. The `limited` networking experiment with `allowed_hosts=[]` is pending `uv run csv-analyst setup` in an environment with a key.

## SDK observations

- 2026-09-28, `anthropic==1.9.0` SDK source/introspection: `Agents.create(name, model, system, tools, metadata)`, `Agents.retrieve(agent_id)`, `Agents.update(agent_id, version, ...)`, `Versions.list(agent_id)`, and `Environments.create(name, config)`, `retrieve(environment_id)`, `archive(environment_id)` are available. Agent responses expose integer `version` and nullable `archived_at`; Environment responses expose nullable `archived_at` and `config`. The SDK typing permits an empty `allowed_hosts` sequence, but server acceptance remains unverified.
- 2026-09-28, `anthropic==1.9.0` async SDK source/introspection: `AsyncEvents.stream(session_id)` is awaitable and returns `AsyncStream[BetaManagedAgentsStreamSessionEvents]`; `AsyncStream` supports `async with`, `async for`, and `close()`. `AsyncFiles.download` returns `AsyncBinaryAPIResponse`, whose `write_to_file(path)` is async. `AsyncFiles.list` returns an async paginator. Server behavior remains unverified without an API key.
