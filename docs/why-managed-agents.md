# Why Managed Agents for csv-analyst

The [Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview) describes a hosted agent harness, isolated sandboxes, saved configuration, and persistent sessions. This project puts those capabilities in a small local application. The pointers below name where each benefit in implementation plan §2 appears.

| Platform benefit | Concrete evidence in this repository |
|---|---|
| Hosted agent loop and harness | `runner.run_session` sends one `user.message` and consumes events; there is no model/tool-dispatch loop. [Overview](https://platform.claude.com/docs/en/managed-agents/overview). |
| Isolated sandbox per session | `orchestrator.run_many` starts one session per CSV; `orchestrator.check_isolation` checks each manifest's `uploads_seen` and exclusive marker. Run the three-fixture Demo in `README.md`. [Cloud environments](https://platform.claude.com/docs/en/managed-agents/environments). |
| Saved, versioned Agent | `resources.ensure_agent` creates or updates the saved Agent; `csv-analyst resources` lists versions; `run --agent-version 1` pins an older one. [Agent setup](https://platform.claude.com/docs/en/managed-agents/agent-setup). |
| Reusable Environment | `resources.ensure_environment` creates one cloud configuration used by every `platform.SdkSessionPlatform.create_session`. Re-running `setup` reports unchanged. [Environments](https://platform.claude.com/docs/en/managed-agents/environments). |
| Built-in tools and permission policy | `agent_spec.build_agent_spec` enables bash and file tools while disabling web tools. `prompts.build_user_message` asks for Python analysis inside the sandbox. [Tools](https://platform.claude.com/docs/en/managed-agents/tools), [permission policies](https://platform.claude.com/docs/en/managed-agents/permission-policies). |
| Custom Skill | `skills/csv-report/SKILL.md` and its profiler script define report conventions; `resources.ensure_skill` uploads a version, then attaches it to the Agent. [Skills](https://platform.claude.com/docs/en/managed-agents/skills). |
| Files in and out | `platform.SdkSessionPlatform.upload_file` and `create_session` mount each CSV; `outputs.collect` lists scoped output files and downloads the validated report, charts, script, and manifest. [Files](https://platform.claude.com/docs/en/managed-agents/files). |
| Streaming and server-side history | `events.normalize` feeds the CLI and web SSE; `runner.tail_session` opens a stream, lists persisted events, and deduplicates IDs. [Event stream](https://platform.claude.com/docs/en/managed-agents/events-and-streaming). |
| Stateful sessions | `runner.ask_session` sends a follow-up to the same idle session, then collects numbered artifacts. The Demo asks for a regional breakdown without uploading sales again. [Resume](https://platform.claude.com/docs/en/managed-agents/events-and-streaming). |
| Hard budget and usage | `platform.SdkSessionPlatform.create_session` sets `max_list_cost`; `runner.resume_budget_session` raises it; `orchestrator.RunSummary` stores per-session `list_cost_cents` and `active_seconds`. [Budgets](https://platform.claude.com/docs/en/managed-agents/budgets). |
| Observability | `csv-analyst tail <session_id>` reconnects to history; the Demo also points to the Console's Managed Agents → Sessions viewer. [Event stream](https://platform.claude.com/docs/en/managed-agents/events-and-streaming). |
| Token plus runtime pricing | `costs.format_cost` and `RunSummary` show list cost; the README explains the separate running-time charge. [Pricing](https://platform.claude.com/docs/en/about-claude/pricing). |

## What we did not have to write

- A model tool loop or tool dispatcher: the hosted harness runs bash, file operations, and Python analysis.
- A container provisioner or isolation layer: each session gets its own sandbox.
- A custom file transport: uploads, mounts, scoped output listing, and downloads use the Files API.
- Conversation and sandbox-state persistence: idle sessions can resume, with a documented 30-day sandbox lifetime.
- A client-enforced cost cap: the service pauses work at a session budget and reports cumulative usage.

With the [Messages API](https://platform.claude.com/docs/en/managed-agents/overview), an application would own the agent loop and tool dispatch, and would need its own sandbox, file transfer, persistence, and budget enforcement. The [Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) supplies an agent loop in a process we operate, but we would still operate the runtime and isolation. Managed Agents hosts those pieces, while this repo focuses on CSV validation, prompts, streamed presentation, artifact checks, and local UX.
