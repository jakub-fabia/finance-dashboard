#!/usr/bin/env python3
"""Fetch monthly Polish CPI y/y from GUS api-sdp and write to /data/cpi.csv.

The y/y CPI series is split across two indicator IDs on api-sdp:
  * 2728 — current (in-progress) year only
  * 1832 — historic archive (closed years)

This script hits both: 1832 for past years, 2728 for the running year, falling
back to whichever serves a given year. Values are reported as an index where
"analogous month previous year = 100" — so value=102.1 means +2.1% y/y. We
persist both the raw index and the derived y/y pct change.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# id-okres 247 = M01 .. 258 = M12. Anything past that is cumulative (M01-02
# etc.) or quarterly and we skip it.
OKRES_TO_MONTH = {247 + i: i + 1 for i in range(12)}

INDICATOR_CURRENT_YEAR = 2728
INDICATOR_HISTORIC = 1832
API_BASE = "https://api-sdp.stat.gov.pl/api/indicators/indicator-data-indicator"


def log(msg: str) -> None:
    print(f"[gus-cpi] {msg}", file=sys.stderr, flush=True)


def _fetch(indicator: int, year: int) -> list[dict] | None:
    url = f"{API_BASE}?id-wskaznik={indicator}&id-rok={year}&lang=pl"
    # The endpoint enforces a short-window rate limit on top of its 7d quota;
    # retry with exponential backoff on 429 a few times before giving up.
    delay = 1.0
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 and attempt < 4:
                log(f"429 on indicator {indicator} year {year} — backoff {delay:.1f}s")
                time.sleep(delay)
                delay *= 2
                continue
            raise
        return data if isinstance(data, list) else None
    return None


def fetch_year(year: int, current_year: int) -> list[dict]:
    """Past years live in 1832 (historic archive), the running year in 2728.
    Pick the right one up front to avoid burning rate limits on 404 probes."""
    indicator = INDICATOR_CURRENT_YEAR if year == current_year else INDICATOR_HISTORIC
    records = _fetch(indicator, year) or []
    if not records and indicator == INDICATOR_CURRENT_YEAR:
        # Year boundary edge case: GUS may have moved this year into the
        # historic indicator already.
        records = _fetch(INDICATOR_HISTORIC, year) or []
    return records


def main() -> int:
    out = Path(os.environ.get("CPI_OUTPUT_FILE", "/data/cpi.csv"))
    start = int(os.environ.get("CPI_START_YEAR", "2022"))
    end = datetime.now().year

    rows: list[dict] = []
    for y in range(start, end + 1):
        if y > start:
            time.sleep(0.6)  # gentle pacing to stay under per-second cap
        records = fetch_year(y, end)
        kept = 0
        for rec in records:
            month = OKRES_TO_MONTH.get(rec.get("id-okres"))
            if month is None:
                continue
            value = rec.get("wartosc")
            if value is None:
                continue
            rows.append({
                "period": f"{y}-{month:02d}",
                "year": y,
                "month": month,
                "cpi_index": value,
                "cpi_yoy_pct": round(value - 100.0, 2),
            })
            kept += 1
        log(f"year {y}: {kept} monthly rows")

    if not rows:
        log("no data fetched — leaving file untouched")
        return 1

    rows.sort(key=lambda r: (r["year"], r["month"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["period", "year", "month", "cpi_index", "cpi_yoy_pct"],
            delimiter=";",
        )
        w.writeheader()
        w.writerows(rows)
    tmp.replace(out)
    log(f"wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
