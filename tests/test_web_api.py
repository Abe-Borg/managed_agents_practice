from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from csv_analyst.cli import app as cli_app
from csv_analyst.config import Settings
from csv_analyst.platform import OutputFileInfo, SessionInfo
from csv_analyst.web.app import create_app
from tests.fakes import FakeSessionPlatform


class WebFake(FakeSessionPlatform):
    def __init__(self, key: str = "") -> None:
        super().__init__(
            [
                {
                    "type": "agent.message",
                    "content": [{"type": "text", "text": f"{key} file_hidden123"}],
                },
                {
                    "type": "session.usage",
                    "usage": {"list_cost": {"amount": "3"}, "active_seconds": 1.2},
                },
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]
        )
        self.key = key

    async def create_session(
        self,
        agent_id: str,
        environment_id: str,
        file_id: str,
        input_name: str,
        budget_cents: int | None,
        run_id: str,
        *,
        agent_version: int | None = None,
        model: str | None = None,
    ) -> SessionInfo:
        base = await super().create_session(
            agent_id,
            environment_id,
            file_id,
            input_name,
            budget_cents,
            run_id,
            agent_version=agent_version,
            model=model,
        )
        self.session_title = f"csv-analyst: {input_name}"
        self.session_metadata = {"app": "csv-analyst", "run_id": run_id}
        chart = "chart_01_values.png"
        names = ["report.md", "analysis.py", chart, "manifest.json"]
        self.output_schedule = [[OutputFileInfo(name, name) for name in names]]
        self.output_payloads = {
            "report.md": f"# Report\n\n![Chart]({chart})\n\n<script>{self.key} file_hidden123</script>".encode(),
            "analysis.py": b"print('ok')",
            chart: b"\x89PNG\r\n\x1a\n",
            "manifest.json": json.dumps(
                {
                    "input_file": input_name,
                    "uploads_seen": [input_name],
                    "markers_seen_before_write": [],
                    "exclusive_marker_created": True,
                    "rows": 1,
                    "columns": 1,
                    "charts": [chart],
                    "summary": "ok",
                    "skill_used": True,
                }
            ).encode(),
        }
        return replace(base, id=f"sesn_{Path(input_name).stem}")


def web_client(tmp_path: Path, *, key: str = "fake-secret-value") -> TestClient:
    settings = Settings(key, "claude-haiku-4-5", 100, 3, 10)
    app = create_app(
        settings=settings,
        platform_factory=lambda: WebFake(key),
        output_root=tmp_path / "runs",
        agent_id="agent_fake",
        environment_id="env_fake",
    )
    return TestClient(app)


def completed(client: TestClient, run_id: str) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.01)
    raise AssertionError("run did not complete")


def test_three_uploads_replay_order_and_reports(tmp_path: Path) -> None:
    with web_client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            files=[
                ("files", (f"{label}.csv", b"x\n1\n", "text/csv")) for label in "abc"
            ],
            data={"budget_cents": "50"},
        )
        assert response.status_code == 202
        run = response.json()
        assert run["labels"] == ["a", "b", "c"]
        run_id = run["run_id"]
        summary = completed(client, run_id)
        assert len(summary["sessions"]) == 3
        assert summary["isolation_passed"] is True
        assert summary["total_list_cost_cents"] == 9

        stream = client.get(f"/api/runs/{run_id}/events")
        assert stream.status_code == 200
        ids = [
            int(line.removeprefix("id: "))
            for line in stream.text.splitlines()
            if line.startswith("id: ")
        ]
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in stream.text.splitlines()
            if line.startswith("data: ")
        ]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))
        assert {event["label"] for event in payloads if event["kind"] == "done"} == {
            "a",
            "b",
            "c",
        }
        resumed = client.get(
            f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(ids[-2])}
        )
        assert resumed.text.count("data: ") == 1
        assert (
            client.get(f"/api/runs/{run_id}/events?after={ids[-2]}").text.count(
                "data: "
            )
            == 1
        )

        report = client.get(f"/api/runs/{run_id}/a/report")
        assert report.status_code == 200
        assert f"/api/runs/{run_id}/a/artifacts/chart_01_values.png" in report.text
        assert "<script>" not in report.text
        assert "&lt;script&gt;" in report.text
        image = client.get(f"/api/runs/{run_id}/a/artifacts/chart_01_values.png")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"


def test_followup_and_budget_routes_reject_unknown_session(tmp_path: Path) -> None:
    with web_client(tmp_path) as client:
        assert (
            client.post(
                "/api/sessions/unknown/ask", json={"question": "why?"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/sessions/unknown/raise-budget", json={"to_cents": 50}
            ).status_code
            == 404
        )


def test_followup_uses_same_run_channel_and_serves_new_report(tmp_path: Path) -> None:
    fake = WebFake()
    app = create_app(
        settings=Settings("fake-key", "claude-haiku-4-5", 100, 3, 10),
        platform_factory=lambda: fake,
        output_root=tmp_path / "runs",
        agent_id="agent_fake",
        environment_id="env_fake",
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/runs", files={"files": ("tiny.csv", b"x\n1\n", "text/csv")}
        )
        run_id = response.json()["run_id"]
        completed(client, run_id)
        before = client.get(f"/api/runs/{run_id}/events").text.count("data: ")
        names = [
            "followup_1_report.md",
            "followup_1_chart_01_next.png",
            "followup_1_manifest.json",
        ]
        initial = fake.output_schedule[0]
        fake.output_schedule = [
            initial,
            [*initial, *(OutputFileInfo(name, name) for name in names)],
        ]
        fake.list_calls = 0
        fake.output_payloads.update(
            {
                names[0]: b"# Follow-up answer",
                names[1]: b"\x89PNG\r\n\x1a\n",
                names[2]: json.dumps({"files": names[:2]}).encode(),
            }
        )
        response = client.post(
            "/api/sessions/sesn_tiny/ask", json={"question": "What next?"}
        )
        assert response.status_code == 202
        for _ in range(100):
            if "Follow-up answer" in client.get(f"/api/runs/{run_id}/tiny/report").text:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("follow-up report did not arrive")
        assert (
            client.get(f"/api/runs/{run_id}/tiny/artifacts/{names[1]}").status_code
            == 200
        )
        assert client.get(f"/api/runs/{run_id}/events").text.count("data: ") > before


def test_raise_budget_collects_paused_artifacts(tmp_path: Path) -> None:
    fake = WebFake()
    fake.events = [
        {"type": "session.usage", "usage": {"list_cost": {"amount": "6"}}},
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}},
    ]
    fake.history_events = fake.events.copy()
    app = create_app(
        settings=Settings("fake-key", "claude-haiku-4-5", 5, 3, 10),
        platform_factory=lambda: fake,
        output_root=tmp_path / "runs",
        agent_id="agent_fake",
        environment_id="env_fake",
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/runs", files={"files": ("tiny.csv", b"x\n1\n", "text/csv")}
        )
        run_id = response.json()["run_id"]
        assert completed(client, run_id)["sessions"][0]["status"] == "paused_budget"
        fake.events = [
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}
        ]
        response = client.post(
            "/api/sessions/sesn_tiny/raise-budget", json={"to_cents": 50}
        )
        assert response.status_code == 202
        for _ in range(100):
            summary = completed(client, run_id)
            if summary["sessions"][0]["status"] == "completed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("budget resume did not finish")
        assert fake.updated_budget == 50
        assert client.get(f"/api/runs/{run_id}/tiny/report").status_code == 200
        events = client.get(f"/api/runs/{run_id}/events").text
        assert '"label": "tiny"' in events
        assert '"stop_reason": "end_turn"' in events


def test_serve_binds_loopback(monkeypatch: Any) -> None:
    import uvicorn

    import csv_analyst.web.app as web_app

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(web_app, "create_app", lambda: object())
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, *, host, port, log_level: calls.append((host, port)),
    )
    result = CliRunner().invoke(cli_app, ["serve", "--port", "8766"])
    assert result.exit_code == 0
    assert calls == [("127.0.0.1", 8766)]
