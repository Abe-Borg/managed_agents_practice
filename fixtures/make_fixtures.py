"""Regenerate the small, deterministic CSV files used by demos and tests."""

from __future__ import annotations

import csv
import random
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent
START_DATE = date(2026, 1, 1)
SEED = 20260928


def write_csv(
    name: str, columns: tuple[str, ...], rows: Iterable[tuple[object, ...]]
) -> None:
    """Write stable UTF-8 bytes, including stable newlines, on every platform."""
    with (FIXTURES_DIR / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def make_tiny() -> None:
    rng = random.Random(SEED + 1)
    regions = ("North", "South", "East", "West")
    products = (("Notebook", 12), ("Mug", 9), ("Tote", 18))
    rows = []
    for index in range(10):
        product, price = products[index % len(products)]
        units = rng.randint(1, 8)
        rows.append(
            (
                (START_DATE + timedelta(days=index)).isoformat(),
                regions[index % len(regions)],
                product,
                units,
                f"{units * price:.2f}",
            )
        )
    write_csv("tiny.csv", ("date", "region", "product", "units", "revenue"), rows)


def make_sales() -> None:
    rng = random.Random(SEED + 2)
    regions = ("North", "South", "East", "West")
    products = (("Notebook", 12), ("Mug", 9), ("Tote", 18), ("Pen Set", 7))
    rows = []
    for day in range(30):
        for region in regions:
            product, price = products[rng.randrange(len(products))]
            units = rng.randint(2, 24)
            rows.append(
                (
                    (START_DATE + timedelta(days=day)).isoformat(),
                    region,
                    product,
                    units,
                    f"{units * price:.2f}",
                )
            )
    write_csv("sales.csv", ("date", "region", "product", "units", "revenue"), rows)


def make_weather() -> None:
    rng = random.Random(SEED + 3)
    cities = (("Seattle", 75), ("Portland", 85), ("Phoenix", 195))
    rows = []
    for day in range(30):
        for city, average_tenths in cities:
            temp_tenths = average_tenths + rng.randint(-55, 55)
            precip_tenths = 0 if rng.randrange(5) < 3 else rng.randint(1, 120)
            rows.append(
                (
                    (START_DATE + timedelta(days=day)).isoformat(),
                    city,
                    f"{temp_tenths / 10:.1f}",
                    f"{precip_tenths / 10:.1f}",
                )
            )
    write_csv("weather.csv", ("date", "city", "temp_c", "precip_mm"), rows)


def make_web_traffic() -> None:
    rng = random.Random(SEED + 4)
    pages = ("/", "/products", "/pricing", "/blog")
    rows = []
    for day in range(30):
        for page in pages:
            visits = rng.randint(80, 500)
            bounce_percent = rng.randint(18, 76)
            rows.append(
                (
                    (START_DATE + timedelta(days=day)).isoformat(),
                    page,
                    visits,
                    f"0.{bounce_percent:02d}",
                )
            )
    write_csv("web_traffic.csv", ("date", "page", "visits", "bounce_rate"), rows)


def main() -> None:
    make_tiny()
    make_sales()
    make_weather()
    make_web_traffic()


if __name__ == "__main__":
    main()
