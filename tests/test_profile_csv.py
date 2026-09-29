from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "csv-report" / "scripts" / "profile_csv.py"


@pytest.mark.parametrize(
    "name", ["tiny.csv", "sales.csv", "weather.csv", "web_traffic.csv"]
)
def test_profiler_outputs_valid_json_for_each_fixture(name: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(ROOT / "fixtures" / name)],
        capture_output=True,
        text=True,
        check=True,
    )
    profile = json.loads(completed.stdout)
    assert profile["rows"] > 0
    assert profile["column_count"] == len(profile["columns"]) > 0
    assert set(profile["dtypes"]) == set(profile["columns"])
    assert set(profile["null_counts"]) == set(profile["columns"])
    assert all(
        0 <= count <= profile["rows"] for count in profile["null_counts"].values()
    )
    assert set(profile["numeric_describe"]) <= set(profile["columns"])
    assert set(profile["top_values"]) <= set(profile["columns"])
