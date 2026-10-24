#!/usr/bin/env python3
"""Example plugin: a savings account with a fixed rate → holdings/savings.csv.

Input, DATA_DIR/savings_deposits.csv (`date;amount`, negative = withdrawal):

  date;amount
  2026-01-05;5000
  2026-03-10;1000

Interest accrues daily on the balance × RATE / 365 and is credited on the 1st
of each month (so it compounds monthly). BELKA of the interest is taken off
the value, as if it were withheld. Copy this file to plugins/<name>.py to use
it; see plugins/README.md for the contract.
"""
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
INPUT = DATA_DIR / "savings_deposits.csv"
OUTPUT = DATA_DIR / "holdings" / "savings.csv"
LABEL = "Savings"
RATE = 0.04    # 4% a year
BELKA = 0.19


def main() -> int:
    if not INPUT.exists():
        print(f"[savings] {INPUT} missing — nothing to write", file=sys.stderr)
        return 0
    moves: dict[date, float] = {}
    with INPUT.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            d = date.fromisoformat(row["date"])
            moves[d] = moves.get(d, 0.0) + float(row["amount"])
    if not moves:
        return 0

    rows, balance, accrued, earned = [], 0.0, 0.0, 0.0
    d, today = min(moves), date.today()
    while d <= today:
        if d.day == 1:
            balance += accrued
            accrued = 0.0
        balance += moves.get(d, 0.0)
        interest = balance * RATE / 365
        accrued += interest
        earned += interest
        kept = earned * (1 - BELKA)
        rows.append([d.isoformat(), f"{balance + accrued - earned * BELKA:.2f}", f"{kept:.2f}"])
        d += timedelta(days=1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        f.write(f"# label: {LABEL}\n")
        w = csv.writer(f, delimiter=";")
        w.writerow(["date", "value", "profit"])
        w.writerows(rows)
    tmp.replace(OUTPUT)
    print(f"[savings] {len(rows)} days → {OUTPUT} (value {rows[-1][1]})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
