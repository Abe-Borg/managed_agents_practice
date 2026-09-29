from __future__ import annotations

from pathlib import Path

from tests.test_web_api import completed, web_client


def test_upload_restrictions_and_artifact_allowlist(tmp_path: Path) -> None:
    with web_client(tmp_path) as client:
        wrong = client.post(
            "/api/runs", files={"files": ("notes.txt", b"x", "text/plain")}
        )
        assert wrong.status_code == 400
        big = client.post(
            "/api/runs",
            files={"files": ("big.csv", b"x" * (1024 * 1024 + 1), "text/csv")},
        )
        assert big.status_code == 413
        traversal = client.post(
            "/api/runs", files={"files": ("../bad.csv", b"x", "text/csv")}
        )
        assert traversal.status_code == 400
        duplicate = client.post(
            "/api/runs",
            files=[
                ("files", ("a.csv", b"x", "text/csv")),
                ("files", ("A.csv", b"x", "text/csv")),
            ],
        )
        assert duplicate.status_code == 400

        response = client.post(
            "/api/runs", files={"files": ("safe.csv", b"x\n1\n", "text/csv")}
        )
        run_id = response.json()["run_id"]
        completed(client, run_id)
        extra = tmp_path / "runs" / run_id / "safe" / "private.txt"
        extra.write_text("not collected", encoding="utf-8")
        assert (
            client.get(f"/api/runs/{run_id}/safe/artifacts/private.txt").status_code
            == 404
        )
        assert client.get(
            f"/api/runs/{run_id}/safe/artifacts/%2E%2E%2F%2Eenv"
        ).status_code in {400, 404}
        assert client.get(
            f"/api/runs/{run_id}/safe/artifacts/..%2F..%2F.env"
        ).status_code in {400, 404}


def test_fake_key_never_reaches_api_body(tmp_path: Path) -> None:
    secret = "fake-secret-value"
    with web_client(tmp_path, key=secret) as client:
        response = client.post(
            "/api/runs", files={"files": ("safe.csv", b"x\n1\n", "text/csv")}
        )
        run_id = response.json()["run_id"]
        completed(client, run_id)
        paths = [
            f"/api/runs/{run_id}",
            f"/api/runs/{run_id}/events",
            f"/api/runs/{run_id}/safe/report",
            f"/api/runs/{run_id}/safe/artifacts/report.md",
        ]
        for path in paths:
            result = client.get(path)
            assert result.status_code == 200
            assert secret not in result.text
            assert "file_hidden123" not in result.text


def test_cross_origin_post_is_rejected(tmp_path: Path) -> None:
    with web_client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            files={"files": ("safe.csv", b"x\n1\n", "text/csv")},
            headers={"Origin": "https://untrusted.example"},
        )
        assert response.status_code == 403
