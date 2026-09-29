"""Print a deterministic JSON profile for one CSV file."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path


def profile_csv(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        if not columns:
            raise ValueError("CSV has no header")
        rows = list(reader)

    values: dict[str, list[str]] = {name: [] for name in columns}
    null_counts = {name: 0 for name in columns}
    for row in rows:
        for name in columns:
            value = row.get(name)
            cleaned = value.strip() if isinstance(value, str) else ""
            if cleaned:
                values[name].append(cleaned)
            else:
                null_counts[name] += 1

    dtypes: dict[str, str] = {}
    numeric_describe: dict[str, dict[str, float | int]] = {}
    top_values: dict[str, list[dict[str, str | int]]] = {}
    for name in columns:
        populated = values[name]
        numbers: list[float] = []
        for value in populated:
            try:
                number = float(value)
            except ValueError:
                break
            if not math.isfinite(number):
                break
            numbers.append(number)
        if populated and len(numbers) == len(populated):
            dtypes[name] = "numeric"
            numeric_describe[name] = {
                "count": len(numbers),
                "min": min(numbers),
                "max": max(numbers),
                "mean": statistics.fmean(numbers),
                "median": statistics.median(numbers),
            }
        else:
            dtypes[name] = "string"

        counts = Counter(populated)
        if 0 < len(counts) <= 10:
            top_values[name] = [
                {"value": value, "count": count}
                for value, count in sorted(
                    counts.items(), key=lambda item: (-item[1], item[0])
                )[:5]
            ]

    return {
        "rows": len(rows),
        "columns": columns,
        "column_count": len(columns),
        "dtypes": dtypes,
        "null_counts": null_counts,
        "numeric_describe": numeric_describe,
        "top_values": top_values,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: profile_csv.py <csv>", file=sys.stderr)
        return 2
    try:
        result = profile_csv(Path(sys.argv[1]))
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Cannot profile CSV: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
