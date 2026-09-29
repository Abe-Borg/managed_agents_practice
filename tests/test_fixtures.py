from __future__ import annotations

import csv
from pathlib import Path

import pytest

from fixtures import make_fixtures

ROOT = Path(__file__).resolve().parents[1]


def test_generated_fixtures_match_committed_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(make_fixtures, "FIXTURES_DIR", tmp_path)
    make_fixtures.main()
    for name in ("tiny.csv", "sales.csv", "weather.csv", "web_traffic.csv"):
        assert (tmp_path / name).read_bytes() == (ROOT / "fixtures" / name).read_bytes()


def test_fixture_shapes_are_small_and_expected() -> None:
    expected = {
        "tiny.csv": (10, ["date", "region", "product", "units", "revenue"]),
        "sales.csv": (120, ["date", "region", "product", "units", "revenue"]),
        "weather.csv": (90, ["date", "city", "temp_c", "precip_mm"]),
        "web_traffic.csv": (120, ["date", "page", "visits", "bounce_rate"]),
    }
    for name, (row_count, headers) in expected.items():
        with (ROOT / "fixtures" / name).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == headers
            assert len(list(reader)) == row_count
