#!/usr/bin/env python3
"""Write a complete set of FAKE input files for the dashboard into a directory.

Every number, name and IBAN here is invented (fixed random seed, so the demo
looks the same every run). It produces what the jobs would have written —
xtb_rebuilt.csv, xtb_holdings.csv, transactions.csv, bonds.csv, cpi.csv,
nbp_rates.csv — plus category_rules.csv, tx_overrides.csv and a savings
account through plugins/examples/fixed_rate_savings.py (holdings/savings.csv),
so build_dashboard.py can run on it:

  python3 demo/make_demo_data.py demo-data
  DATA_DIR=demo-data python3 dashboard/build_dashboard.py     # needs pandas
  # or with Docker, see README.md "Try it with fake data".

Stdlib only. Writes are atomic (tmp → replace), like the real jobs.
"""
import csv
import math
import os
import random
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
rng = random.Random(7)
OWN_IBAN = "PL00100000000000000000000001"      # fake: the main bank account


def write(path: Path, header, rows, comment: str = "") -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        if comment:
            f.write(comment)
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        w.writerows(rows)
    tmp.replace(path)


def months_back(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    return date(y, m + 1, min(d.day, 28))


# --- Stocks (what xtb/rebuild_xtb.py writes) -----------------------------------

def stocks(out: Path, now: datetime) -> None:
    start = (now - timedelta(days=1460)).replace(minute=0, second=0, microsecond=0)
    times, t = [], start
    while t < now:
        times.append(t)
        t += timedelta(hours=1)
    fine_from = now - timedelta(days=59)
    t = fine_from.replace(hour=0, minute=0, second=0, microsecond=0)
    while t < now:
        if t.weekday() < 5 and 9 <= t.hour < 18 and t.minute:
            times.append(t)
        t += timedelta(minutes=15)
    times = sorted(set(times)) + [now.replace(microsecond=0)]

    price, units, deposits, rows, last_month = 100.0, 0.0, 0.0, [], None
    for t in times:
        # Markets move on weekdays, 9–18; a deposit buys units on the 10th.
        if t.weekday() < 5 and 9 <= t.hour < 18:
            step = 0.25 if t >= fine_from and t.minute else 1.0
            price *= math.exp(rng.gauss(0.00006 * step, 0.0035 * math.sqrt(step)))
        if (t.year, t.month) != last_month and t.day >= 10:
            last_month = (t.year, t.month)
            amount = 4000.0
            deposits += amount
            units += amount / price
        value = units * price
        rows.append([t.isoformat(), 0, f"{value:.2f}", f"{deposits:.2f}", f"{value - deposits:.2f}", "0.00"])
    write(out / "xtb_rebuilt.csv",
          ["captured_at", "after_export", "total_pln", "net_deposits_pln", "profit_pln", "pending_pln"], rows)

    # Split today's value over two accounts and three instruments.
    total, profit = float(rows[-1][2]), float(rows[-1][4])
    plan = [  # account, kind, ticker, name, currency, local price, share, open gain
        ("10000001", "PLN", "ETFBM40TR.PL", "Beta ETF mWIG40TR", "PLN", 132.80, 0.31, 0.24),
        ("10000001", "PLN", "ETFBSPXPL.PL", "Beta ETF S&P 500 PLN-Hedged", "PLN", 245.10, 0.21, 0.33),
        ("10000002", "USD", "VTI.US", "Vanguard Total Stock Market ETF", "USD", 286.40, 0.45, 0.29),
    ]
    fx = {"PLN": 1.0, "USD": 3.94}
    hold = []
    for acct, kind, ticker, name, ccy, px, share, gain in plan:
        value = total * share
        qty = value / (px * fx[ccy])
        hold.append([acct, kind, ticker, name, f"{qty:.4f}", f"{px:.4f}", ccy, f"{value:.2f}", f"{value / (1 + gain):.2f}"])
    cash = total - sum(total * p[6] for p in plan)
    for acct, kind in (("10000001", "PLN"), ("10000002", "USD")):
        hold.append([acct, kind, "CASH", kind, "0", "1", kind, f"{cash / 2:.2f}", f"{cash / 2:.2f}"])
    write(out / "xtb_holdings.csv",
          ["account", "kind", "ticker", "name", "qty", "price", "currency", "value_pln", "cost_pln"], hold)
    print(f"stocks: {len(rows)} points, value {total:,.2f}, profit {profit:,.2f}")


# --- Bonds + the rates they need -----------------------------------------------

def bonds(out: Path, today: date) -> None:
    def name(series: str, bought: date, months: int) -> str:
        m = months_back(bought, -months)
        return f"{series}{m.month:02d}{m.year % 100:02d}/{bought.day}"

    rows = []
    for back, series, months, nominal, rate, margin in (
        (40, "COI", 48, 20000, 0.0650, 0.0125),
        (22, "COI", 48, 12000, 0.0600, 0.0125),
        (9, "DOR", 24, 8000, 0.0560, 0.0015),
    ):
        bought = months_back(today, back).replace(day=rng.randint(2, 27))
        rows.append([name(series, bought, months), nominal, rate, margin])
    write(out / "bonds.csv", ["name", "nominal_pln", "first_period_rate", "margin"], rows,
          comment="# FAKE demo holdings. Format: see docs/SETUP.md, \"Treasury bonds\".\n")

    cpi, yoy, d = [], 16.6, date(2022, 1, 1)
    while d < today.replace(day=1):
        yoy = max(2.0, yoy * 0.93 + rng.uniform(-0.4, 0.4)) if d.year > 2022 else 9 + (d.month * 0.6)
        cpi.append([f"{d:%Y-%m}", d.year, d.month, f"{100 + yoy:.1f}", f"{yoy:.1f}"])
        d = months_back(d, -1)
    write(out / "cpi.csv", ["period", "year", "month", "cpi_index", "cpi_yoy_pct"], cpi)
    write(out / "nbp_rates.csv", ["effective_date", "reference_rate_pct"],
          [["2022-09-08", "6.75"], ["2023-09-07", "6.00"], ["2023-10-05", "5.75"],
           [f"{months_back(today, 7):%Y-%m-%d}", "5.25"]])


# --- Bank transactions + the rules that sort them ------------------------------

MERCHANTS = {
    "groceries": (["FRESHMART 012 WARSZAWA", "GREENGROCER SP. Z O.O.", "CORNER MARKET 7"], 18, 15, 140),
    "eatout": (["CITY BISTRO", "PIZZERIA NAPOLI 2", "SUSHI GARDEN", "BURGER HOUSE"], 6, 25, 120),
    "transportation": (["METRO TICKETS", "FUEL STATION 44", "CITY BIKE"], 5, 6, 220),
    "leisure": (["CINEMA PALACE", "CLIMBING GYM", "BOOKSHOP ATLAS"], 4, 20, 160),
    "subscriptions": (["STREAMFLIX", "MUSICBOX PREMIUM"], 0, 30, 50),
    "shopping": (["HOMEWARE STORE", "ONLINE MARKETPLACE"], 2, 40, 400),
    "health": (["PHARMACY PLUS", "DENTAL CLINIC"], 1, 20, 250),
    "uncategorized": (["SMALL SHOP 21", "MARKET STALL"], 2, 8, 60),
}

RULES = [
    ("exclude", "*", r"\bBROKER XYZ\b"),
    ("rent", "remittance_information", r"\bRENT\b"),
    ("salary", "debtor_name", r"ACME"),
    ("groceries", "creditor_name", r"FRESHMART|GREENGROCER|CORNER MARKET"),
    ("eatout", "creditor_name", r"BISTRO|PIZZERIA|SUSHI|BURGER"),
    ("transportation", "creditor_name", r"METRO|FUEL STATION|CITY BIKE"),
    ("leisure", "creditor_name", r"CINEMA|CLIMBING|BOOKSHOP"),
    ("subscriptions", "creditor_name", r"STREAMFLIX|MUSICBOX"),
    ("shopping", "creditor_name", r"HOMEWARE|MARKETPLACE"),
    ("health", "creditor_name", r"PHARMACY|DENTAL"),
    ("travel", "creditor_name", r"AIRLINE|HOTEL"),
]


def transactions(out: Path, today: date) -> None:
    rows, n = [], 0

    def tx(day: date, cd: str, amount: float, creditor: str, debtor: str, title: str, cred_iban="", bank="main"):
        nonlocal n
        n += 1
        deb_iban = OWN_IBAN if cd == "DBIT" else rng.choice(["PL00200000000000000000000009", ""])
        rows.append([f"{day}", cd, f"{amount:.2f}", "PLN", creditor, debtor, title,
                     cred_iban or (OWN_IBAN if cd == "CRDT" else ""), deb_iban, f"DEMO{n:06d}", bank])

    first = months_back(today.replace(day=1), 12)
    d = first
    while d <= today:
        month_days = [x for x in range(1, 29) if date(d.year, d.month, x) <= today]
        if not month_days:
            break
        day = lambda x: date(d.year, d.month, x)
        if 10 in month_days:
            tx(day(10), "CRDT", rng.uniform(14200, 15100), "ME", "ACME SP. Z O.O.", "Salary")
        if 1 in month_days:
            tx(day(1), "DBIT", 4300, "JOHN LANDLORD", "ME", "RENT apartment")
        if 11 in month_days:
            tx(day(11), "DBIT", 4000, "BROKER XYZ", "ME", "Deposit")
        for cat, (names, count, lo, hi) in MERCHANTS.items():
            k = count if cat != "subscriptions" else len(names)
            for i in range(k):
                who = names[i] if cat == "subscriptions" else rng.choice(names)
                amount = {"STREAMFLIX": 49.0, "MUSICBOX PREMIUM": 23.99}.get(who) or rng.uniform(lo, hi)
                tx(day(rng.choice(month_days)), "DBIT", amount, who, "ME", "Card payment")
        if d.month in (2, 7, 8) and 20 in month_days:
            tx(day(20), "DBIT", rng.uniform(600, 1400), "AIRLINE EXPRESS", "ME", "Tickets")
            tx(day(20), "DBIT", rng.uniform(800, 2000), "HOTEL SEASIDE", "ME", "Stay")
        d = months_back(d, -1)

    rows.sort(key=lambda r: r[0])
    write(out / "transactions.csv",
          ["booking_date", "credit_debit", "amount", "currency", "creditor_name", "debtor_name",
           "remittance_information", "creditor_iban", "debtor_iban", "transaction_id", "bank"], rows)
    write(out / "category_rules.csv", ["category", "field", "pattern"], RULES,
          comment="# FAKE demo rules. First matching row wins; see docs/SETUP.md, \"Categories\".\n")
    write(out / "tx_overrides.csv", ["transaction_id", "category"], [])
    print(f"transactions: {len(rows)}")


def plugin(out: Path, today: date) -> None:
    """A savings account through the example plugin, to show a plugin holding."""
    rows = [[f"{months_back(today, 20)}", "25000"]]
    rows += [[f"{months_back(today, n).replace(day=15)}", "2500"] for n in range(19, 0, -1)]
    write(out / "savings_deposits.csv", ["date", "amount"], rows)
    script = Path(__file__).resolve().parent.parent / "plugins" / "examples" / "fixed_rate_savings.py"
    subprocess.run([sys.executable, str(script)], check=True, env={**os.environ, "DATA_DIR": str(out)})


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TZ)
    stocks(out, now)
    bonds(out, now.date())
    transactions(out, now.date())
    plugin(out, now.date())
    print(f"fake data → {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
