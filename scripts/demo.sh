#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

pause() {
  if [[ -t 0 ]]; then
    read -r -p "$1 Press Enter to continue... " _
  else
    printf '%s\n' "$1"
  fi
}

latest_summary() {
  uv run python -c 'from pathlib import Path; print(max(Path("runs").glob("*/summary.json"), key=lambda p: p.stat().st_mtime))'
}

session_from() {
  uv run python -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(next(row["session_id"] for row in data["sessions"] if row["label"] == sys.argv[2]))' "$1" "$2"
}

run_id_from() {
  uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["run_id"])' "$1"
}

status_from() {
  uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["sessions"][0]["status"])' "$1"
}

if [[ ! -f .env && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  cp .env.example .env
  printf '%s\n' 'Add ANTHROPIC_API_KEY to the local, gitignored .env or your environment, then rerun this script.'
  exit 2
fi

uv sync
uv run csv-analyst doctor
pause 'Saved configuration: setup twice, then inspect Agent versions.'
uv run csv-analyst setup
uv run csv-analyst setup
uv run csv-analyst resources

pause 'Parallel run: watch three live rows, costs, and the isolation table.'
uv run csv-analyst run fixtures/sales.csv fixtures/weather.csv fixtures/web_traffic.csv \
  --max-parallel 3 --budget-cents 100
parallel_summary=$(latest_summary)
parallel_run_id=$(run_id_from "$parallel_summary")
sales_session_id=$(session_from "$parallel_summary" sales)
printf 'Sales report: runs/%s/sales/report.md\n' "$parallel_run_id"
head -n 30 "runs/$parallel_run_id/sales/report.md"

pause 'Stateful follow-up: reuse the sales session and its analysis.py.'
uv run csv-analyst ask "$sales_session_id" 'Break revenue down by region with one chart'

pause 'Budget guardrail: start a new sales session with a five-cent cap.'
uv run csv-analyst run fixtures/sales.csv --budget-cents 5
budget_summary=$(latest_summary)
budget_session_id=$(session_from "$budget_summary" sales)
if [[ $(status_from "$budget_summary") == paused_budget ]]; then
  uv run csv-analyst raise-budget "$budget_session_id" --to-cents 100
else
  printf '%s\n' 'The five-cent run completed before the cap was checked; no resume is needed.'
fi

pause 'Local web UI: upload the three fixtures at a 100-cent cap, then return here.'
uv run csv-analyst serve --port 8765 &
web_pid=$!
trap 'kill "$web_pid" 2>/dev/null || true' EXIT
printf '%s\n' 'Open http://127.0.0.1:8765 in your browser.'
pause 'Inspect live panels, reports, charts, and a sales follow-up.'
kill "$web_pid" 2>/dev/null || true
wait "$web_pid" 2>/dev/null || true
trap - EXIT

pause 'Reconnect to the sales history and archive the parallel demo run.'
uv run csv-analyst tail "$sales_session_id"
uv run csv-analyst cleanup --run "$parallel_run_id"
printf '%s\n' 'Demo complete. See runs/ for reports, charts, manifests, and measured costs.'
