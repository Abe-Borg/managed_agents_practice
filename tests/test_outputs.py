from __future__ import annotations

import json
from pathlib import Path

import pytest

from csv_analyst.outputs import OutputError, collect
from csv_analyst.platform import OutputFileInfo
from tests.fakes import FakeSessionPlatform


@pytest.mark.asyncio
async def test_collect_waits_for_manifest_and_ignores_extra_files(
    tmp_path: Path,
) -> None:
    platform = FakeSessionPlatform()
    report = OutputFileInfo("f_report", "report.md")
    script = OutputFileInfo("f_script", "analysis.py")
    chart = OutputFileInfo("f_chart", "chart_01_sales.png")
    extra_chart = OutputFileInfo("f_extra_chart", "chart_02_unlisted.png")
    manifest = OutputFileInfo("f_manifest", "manifest.json")
    extra = OutputFileInfo("f_extra", "private.txt")
    platform.output_schedule = [
        [report],
        [report, script, chart, extra_chart, manifest, extra],
    ]
    platform.output_payloads = {
        "f_report": b"# Report",
        "f_script": b"print('hello')",
        "f_chart": b"\x89PNG\r\n\x1a\n",
        "f_manifest": json.dumps(
            {
                "input_file": "tiny.csv",
                "uploads_seen": ["tiny.csv"],
                "markers_seen_before_write": [],
                "rows": 10,
                "columns": 2,
                "charts": ["chart_01_sales.png"],
                "summary": "Small fixture",
            }
        ).encode(),
    }

    result = await collect(
        platform, "sesn_fake", tmp_path / "out", "tiny.csv", poll_s=0
    )

    assert platform.list_calls == 2
    assert len(result.files) == 4
    assert result.ignored == ("chart_02_unlisted.png", "private.txt")
    assert not (result.directory / "private.txt").exists()


@pytest.mark.asyncio
async def test_collect_rejects_manifest_with_unexpected_upload(tmp_path: Path) -> None:
    platform = FakeSessionPlatform()
    platform.output_schedule = [[OutputFileInfo("manifest", "manifest.json")]]
    platform.output_payloads["manifest"] = json.dumps(
        {"input_file": "tiny.csv", "uploads_seen": ["other.csv"]}
    ).encode()
    with pytest.raises(OutputError, match="unexpected uploads"):
        await collect(platform, "sesn_fake", tmp_path / "out", "tiny.csv", max_wait_s=0)
