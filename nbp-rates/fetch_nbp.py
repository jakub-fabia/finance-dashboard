#!/usr/bin/env python3
"""Fetch NBP reference rate (stopa referencyjna) history and write to
/data/nbp_rates.csv.

NBP publishes two XML feeds we use:
  * stopy_procentowe_archiwum.xml — every historical rate change (since 1998)
  * stopy_procentowe.xml          — the currently-in-effect rates

We merge both into one ordered CSV keyed by effective date. Used by
dashboard/build_dashboard.py to value NBP-indexed series (ROR, DOR) — the rate at a period's
start is the most recent rate change ≤ that date.
"""

from __future__ import annotations

import csv
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ARCHIVE_URL = "https://static.nbp.pl/dane/stopy/stopy_procentowe_archiwum.xml"
CURRENT_URL = "https://static.nbp.pl/dane/stopy/stopy_procentowe.xml"


def log(msg: str) -> None:
    print(f"[nbp-rates] {msg}", file=sys.stderr, flush=True)


def _fetch(url: str) -> bytes:
    # NBP's static server rejects requests that set an Accept header — leave
    # it off and identify with a plain UA.
    req = urllib.request.Request(url, headers={"User-Agent": "finance-jobs/nbp-rates"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_money(s: str) -> float:
    # NBP uses Polish locale: "3,75" -> 3.75
    return float(s.replace(",", "."))


def _parse_archive(xml_bytes: bytes) -> list[tuple[str, float]]:
    """Return list of (effective_date, reference_rate) from the archive feed."""
    root = ET.fromstring(xml_bytes)
    out: list[tuple[str, float]] = []
    for group in root.findall("pozycje"):
        eff = group.get("obowiazuje_od")
        if not eff:
            continue
        for poz in group.findall("pozycja"):
            if poz.get("id") == "ref":
                out.append((eff, _parse_money(poz.get("oprocentowanie", "0"))))
                break
    return out


def _parse_current(xml_bytes: bytes) -> tuple[str, float] | None:
    """Return (effective_date, reference_rate) for the currently-in-effect rate."""
    root = ET.fromstring(xml_bytes)
    for tab in root.findall("tabela"):
        for poz in tab.findall("pozycja"):
            if poz.get("id") == "ref":
                return (
                    poz.get("obowiazuje_od", ""),
                    _parse_money(poz.get("oprocentowanie", "0")),
                )
    return None


def main() -> int:
    out = Path(os.environ.get("NBP_OUTPUT_FILE", "/data/nbp_rates.csv"))

    try:
        archive = _parse_archive(_fetch(ARCHIVE_URL))
    except Exception as e:
        log(f"archive fetch failed: {e!r}")
        return 1
    log(f"archive: {len(archive)} historical rate changes")

    try:
        current = _parse_current(_fetch(CURRENT_URL))
    except Exception as e:
        log(f"current fetch failed (continuing with archive only): {e!r}")
        current = None
    if current:
        log(f"current: {current[1]:.2f}% effective {current[0]}")

    seen: dict[str, float] = {d: r for d, r in archive}
    if current and current[0]:
        seen[current[0]] = current[1]
    rows = sorted(seen.items())

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["effective_date", "reference_rate_pct"])
        for d, r in rows:
            w.writerow([d, f"{r:.2f}"])
    tmp.replace(out)
    log(f"wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
