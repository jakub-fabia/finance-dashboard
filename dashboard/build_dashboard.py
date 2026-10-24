#!/usr/bin/env python3
"""Precompute everything the dashboard shows → dashboard.json.

The page (dashboard/web/) only renders this file; all maths happens here,
whenever an input changes (cron runs it after every job). Inputs, all in
DATA_DIR:

  xtb_rebuilt.csv      XTB value + all-time profit, hourly (xtb/rebuild_xtb.py)
  xtb_holdings.csv     what each XTB account holds now (same job)
  bonds.csv            bond holdings (+ cpi.csv / nbp_rates.csv for the rates)
  transactions.csv     bank transactions (banks/fetch_transactions.py)
  category_rules.csv   `category;field;pattern` — first match wins; category
                       `exclude` drops capital moves (broker, funds)
  tx_overrides.csv     `transaction_id;category` — pins one transaction
  own_accounts.csv     optional `iban;note` — your other accounts: transfers
                       to/from them are not spending or income
  holdings/*.csv       your own holdings, written by scripts in plugins/
                       (see plugins/README.md): `date;value;profit`

How bonds accrue and how transactions are sorted is described in
docs/SETUP.md. Write is atomic (tmp → replace).
"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
OUTPUT_PATH = Path(os.environ.get("DASHBOARD_OUTPUT_FILE", DATA_DIR / "dashboard.json"))
TZ = "Europe/Warsaw"

# Months of spending history sent to the page.
SPENDING_MONTHS = 13


def log(msg: str) -> None:
    print(f"[dashboard] {msg}", file=sys.stderr)


def r2(x) -> float:
    return round(float(x), 2)


# --- Stocks ------------------------------------------------------------------

def load_xtb() -> pd.DataFrame:
    # Spans DST (+01:00 / +02:00 offsets), so parse as UTC and convert.
    df = pd.read_csv(DATA_DIR / "xtb_rebuilt.csv", sep=";")
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True).dt.tz_convert(TZ)
    return df.sort_values("captured_at").reset_index(drop=True)


def stocks_series(xtb: pd.DataFrame) -> list[list[float]]:
    # Trading hours only (nights and weekends are flat), plus the latest
    # point. Times are Warsaw wall-clock seconds: the chart shows them as UTC.
    local = xtb["captured_at"].dt.tz_localize(None)
    t = (local - pd.Timestamp("1970-01-01")).dt.total_seconds().astype("int64")
    keep = (local.dt.day_of_week < 5) & local.dt.hour.between(9, 18)
    keep.iloc[-1] = True
    d = pd.DataFrame({"t": t, "profit": xtb["profit_pln"], "value": xtb["total_pln"]})[keep]
    d = d.drop_duplicates("t", keep="last")
    return [[int(a), r2(b), r2(c)] for a, b, c in zip(d["t"], d["profit"], d["value"])]


# Account kind (export file prefix) → how the page names it, in display order.
XTB_ACCOUNTS = {"IKE": "IKE", "PLN": "Main account", "EUR": "EUR account", "USD": "USD account"}


def stock_accounts() -> list[dict]:
    """What each XTB account holds now (xtb_holdings.csv from the rebuild).
    Dust under 1 zł (fractional leftovers) is dropped."""
    path = DATA_DIR / "xtb_holdings.csv"
    if not path.exists():
        return []
    h = pd.read_csv(path, sep=";", dtype={"account": str})
    h = h[h["value_pln"].abs() >= 1]
    out = []
    for kind, label in XTB_ACCOUNTS.items():
        rows = h[h["kind"] == kind]
        if rows.empty:
            continue
        positions = [{
            "ticker": r.ticker, "name": r.name, "qty": float(r.qty), "price": float(r.price),
            "currency": r.currency, "value": r2(r.value_pln), "profit": r2(r.value_pln - r.cost_pln),
            "profit_pct": r2((r.value_pln / r.cost_pln - 1) * 100) if r.cost_pln else 0.0,
        } for r in rows[rows["ticker"] != "CASH"].sort_values("value_pln", ascending=False).itertuples()]
        cash = rows.loc[rows["ticker"] == "CASH", "value_pln"].sum()
        out.append({"kind": kind, "label": label, "value": r2(rows["value_pln"].sum()),
                    "positions": positions, "cash": r2(cash)})
    return out


# --- Bonds ------------------------------------------------------------------------

SERIES_DEFAULTS = {
    # type: (duration_months, period_months, compounding, lookback, rate_index)
    "OTS": (3,   3,  "no",  0, "cpi"),  # 3-mo fixed, paid at maturity
    "ROR": (12,  1,  "no",  0, "nbp"),  # 1-yr, NBP reference rate
    "DOR": (24,  1,  "no",  0, "nbp"),  # 2-yr, NBP rate + margin
    "TOS": (36,  12, "yes", 0, "cpi"),  # 3-yr fixed, annual compound
    "COI": (48,  12, "no",  2, "cpi"),  # 4-yr CPI-indexed, payout
    "EDO": (120, 12, "yes", 2, "cpi"),  # 10-yr CPI-indexed, annual compound
    "ROS": (72,  12, "yes", 2, "cpi"),  # 6-yr family bond
    "ROD": (144, 12, "yes", 2, "cpi"),  # 12-yr family bond
}
_NAME_RE = re.compile(r"^\s*([A-Z]{3,4})(\d{2})(\d{2})(?:/(\d{1,2}))?\s*$", re.IGNORECASE)


def _from_name(name):
    if not isinstance(name, str):
        return {}
    m = _NAME_RE.match(name)
    if not m:
        return {}
    series = m.group(1).upper()
    mm, yy = int(m.group(2)), int(m.group(3))
    day = int(m.group(4)) if m.group(4) else 1
    if not (1 <= mm <= 12) or not (1 <= day <= 31) or series not in SERIES_DEFAULTS:
        return {"series_type": series}
    duration, period, comp, lookback, rate_index = SERIES_DEFAULTS[series]
    maturity = pd.Timestamp(year=2000 + yy, month=mm, day=1)
    issue_month_start = maturity - pd.DateOffset(months=duration)
    try:
        purchase = issue_month_start.replace(day=day)
    except ValueError:
        purchase = issue_month_start
    return {
        "series_type": series,
        "maturity_date": maturity,
        "purchase_date": purchase,
        "period_months": period,
        "compounding": comp,
        "cpi_lookback_months": lookback,
        "rate_index": rate_index,
    }


def load_bonds():
    path = DATA_DIR / "bonds.csv"
    bonds = pd.DataFrame(columns=["name"])
    if path.exists():
        # Short rows are padded so trailing columns can be omitted.
        lines = [ln.rstrip("\r\n") for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        if lines:
            header = lines[0].split(";")
            rows = []
            for ln in lines[1:]:
                cells = ln.split(";")
                cells = cells + [""] * (len(header) - len(cells)) if len(cells) < len(header) else cells[:len(header)]
                rows.append(cells)
            bonds = pd.DataFrame(rows, columns=header)

    bonds["purchase_date"] = pd.to_datetime(bonds.get("purchase_date"), errors="coerce") \
        if "purchase_date" in bonds.columns else pd.NaT
    for col in ("nominal_pln", "first_period_rate", "margin", "period_months", "cpi_lookback_months"):
        if col not in bonds.columns:
            bonds[col] = pd.NA
        bonds[col] = pd.to_numeric(bonds[col], errors="coerce")
    if "compounding" not in bonds.columns:
        bonds["compounding"] = pd.NA
    bonds["compounding"] = bonds["compounding"].astype("object").where(
        bonds["compounding"].astype(str).str.strip().str.lower().isin(
            ["yes", "y", "true", "1", "t", "no", "n", "false", "0", "f"]), pd.NA)
    if "rate_index" not in bonds.columns:
        bonds["rate_index"] = pd.NA
    bonds["rate_index"] = bonds["rate_index"].astype("object").where(
        bonds["rate_index"].astype(str).str.strip().str.lower().isin(["cpi", "nbp"]), pd.NA)

    if len(bonds):
        derived = bonds["name"].apply(_from_name).apply(pd.Series)
        for col in ("purchase_date", "period_months", "compounding", "cpi_lookback_months", "rate_index"):
            if col in derived.columns:
                bonds[col] = bonds[col].fillna(derived[col])
        for col in ("series_type", "maturity_date"):
            if col in derived.columns:
                bonds[col] = derived[col]

    cpi = pd.read_csv(DATA_DIR / "cpi.csv", sep=";")
    cpi_yoy = pd.Series(pd.to_numeric(cpi["cpi_yoy_pct"], errors="coerce").values, index=cpi["period"].values)
    nbp = pd.read_csv(DATA_DIR / "nbp_rates.csv", sep=";", parse_dates=["effective_date"])
    nbp = nbp.sort_values("effective_date").reset_index(drop=True)
    nbp_rate = pd.Series(pd.to_numeric(nbp["reference_rate_pct"], errors="coerce").values,
                         index=nbp["effective_date"].values)
    return bonds, cpi_yoy, nbp_rate


def bonds_at(bonds, cpi_yoy, nbp_rate, today: pd.Timestamp) -> pd.DataFrame:
    """Walk each bond period-by-period from purchase_date to `today`."""

    def _truthy(x):
        return str(x).strip().lower() in ("yes", "y", "true", "1", "t")

    def _resolve_rate(period_idx, period_start, rate1, margin, rate_index, lookback):
        if period_idx == 0:
            return rate1, "first period"
        if margin is None:
            return rate1, "fixed"
        if rate_index == "nbp":
            nbp_pct = nbp_rate.asof(period_start) if len(nbp_rate) else None
            if nbp_pct is None or pd.isna(nbp_pct):
                return rate1, f"fallback (no NBP rate ≤ {period_start:%Y-%m-%d})"
            return (nbp_pct / 100.0 + margin,
                    f"NBP {nbp_pct:.2f}%" + (f" + {margin*100:.2f}pp" if margin else ""))
        ref = period_start - pd.DateOffset(months=lookback)
        ref_key = f"{ref.year}-{ref.month:02d}"
        cpi_pct = cpi_yoy.get(ref_key)
        if cpi_pct is None or pd.isna(cpi_pct):
            return rate1, f"fallback (no CPI {ref_key})"
        return cpi_pct / 100.0 + margin, f"CPI {ref_key} {cpi_pct:.1f}% + {margin*100:.2f}pp"

    def _compute(row):
        purchase = pd.Timestamp(row["purchase_date"]).normalize()
        nominal = float(row["nominal_pln"])
        rate1 = float(row["first_period_rate"])
        margin = row.get("margin")
        margin = None if pd.isna(margin) else float(margin)
        period_months = int(row.get("period_months") or 12)
        compounding = _truthy(row.get("compounding"))
        lookback = int(row.get("cpi_lookback_months") or 2)
        rate_index = str(row.get("rate_index") or "cpi").lower()

        principal, paid_out, unrealized = nominal, 0.0, 0.0
        period_idx, period_start = 0, purchase
        last_rate, rate_source = rate1, "first period"
        while period_start <= today:
            period_end = period_start + pd.DateOffset(months=period_months)
            rate, rate_source = _resolve_rate(period_idx, period_start, rate1, margin, rate_index, lookback)
            last_rate = rate
            complete = period_end <= today
            # Annual rate; credited interest = principal × rate × years elapsed.
            years_accrued = period_months / 12.0 if complete else (today - period_start).days / 365.0
            period_interest = principal * rate * years_accrued
            if compounding and complete:
                principal += period_interest
            elif not compounding and complete:
                paid_out += period_interest
            else:
                unrealized = period_interest
            if not complete:
                break
            period_start = period_end
            period_idx += 1

        if compounding:
            current_value = principal + unrealized
            accrued = current_value - nominal
        else:
            current_value = nominal + unrealized
            accrued = paid_out + unrealized
        return pd.Series({"current_value_pln": current_value, "accrued_pln": accrued,
                          "current_rate_pct": last_rate * 100, "rate_source": rate_source})

    if not len(bonds):
        return pd.DataFrame(columns=["current_value_pln", "accrued_pln", "current_rate_pct", "rate_source"])
    held = bonds[bonds["purchase_date"] <= today]
    if not len(held):
        return pd.DataFrame(columns=[*bonds.columns, "current_value_pln", "accrued_pln",
                                     "current_rate_pct", "rate_source"])
    return pd.concat([held.reset_index(drop=True), held.apply(_compute, axis=1).reset_index(drop=True)], axis=1)


# --- Transactions -----------------------------------------------------------------

def load_rules():
    rules = pd.read_csv(DATA_DIR / "category_rules.csv", sep=";", comment="#", dtype=str).dropna()
    fields = ["creditor_name", "debtor_name", "remittance_information"]
    return [(re.compile(r.pattern, re.IGNORECASE), fields if r.field == "*" else [r.field], r.category)
            for r in rules.itertuples()]


def load_transactions():
    tx = pd.read_csv(DATA_DIR / "transactions.csv", sep=";", dtype={"transaction_id": str})
    tx["booking_date"] = pd.to_datetime(tx["booking_date"])
    tx["amount"] = pd.to_numeric(tx["amount"], errors="coerce")
    tx["month"] = tx["booking_date"].dt.to_period("M").astype(str)
    rules = load_rules()

    # Internal transfers between own accounts: debtor == creditor by name, the
    # counterparty IBAN is one of ours (between your banks), or the bank calls
    # it an own transfer.
    same_name = (tx["debtor_name"].fillna("").str.strip().str.lower()
                 == tx["creditor_name"].fillna("").str.strip().str.lower())
    both_present = tx["debtor_name"].notna() & tx["creditor_name"].notna()
    iban = lambda c: tx[c].fillna("").astype(str).str.replace(" ", "")
    deb, cred = iban("debtor_iban"), iban("creditor_iban")
    out = tx["credit_debit"].eq("DBIT")
    bank = tx["bank"].fillna("") if "bank" in tx.columns else pd.Series("", index=tx.index)
    own_ibans = {
        deb[out & bank.eq(b) & deb.ne("")].mode().iat[0]
        for b in bank.unique() if (out & bank.eq(b) & deb.ne("")).any()
    } | own_accounts()
    counterparty = cred.where(out, deb)
    own_transfer = counterparty.isin(own_ibans) | tx["remittance_information"].fillna("").str.contains(
        r"przelew\s+własny|internal\s+transfer", case=False, regex=True)
    internal = (same_name & both_present) | own_transfer

    def matches(row, keep):
        for pat, fields, cat in rules:
            if keep(cat) and any(isinstance(row.get(f), str) and pat.search(row[f]) for f in fields):
                return cat
        return None

    excluded = tx.apply(lambda r: matches(r, lambda c: c == "exclude") is not None, axis=1)
    ext = tx[~(internal | excluded)].reset_index(drop=True)
    ext["category"] = ext.apply(lambda r: matches(r, lambda c: c != "exclude") or "uncategorized", axis=1)

    overrides_path = DATA_DIR / "tx_overrides.csv"
    if overrides_path.exists():
        o = pd.read_csv(overrides_path, sep=";", dtype={"transaction_id": str}).dropna(subset=["transaction_id", "category"])
        ext["category"] = ext["transaction_id"].astype(str).map(dict(zip(o["transaction_id"], o["category"]))).fillna(ext["category"])
    return ext


def spending(ext: pd.DataFrame, today: pd.Timestamp) -> dict:
    """Per month: income, spent, spent by category, and what it's compared with.
    The running month is compared with the previous one *up to the same day*
    (e.g. days 1–24 of this month vs 1–24 of last month), a finished month with the whole
    previous month — so a partial month never looks like a big drop."""
    dbit_all = ext[ext["credit_debit"] == "DBIT"]

    def by_cat(rows):
        s = rows.groupby("category")["amount"].sum().sort_values(ascending=False)
        return {k: r2(v) for k, v in s.items() if v > 0}

    months = sorted(ext["month"].unique(), reverse=True)[:SPENDING_MONTHS]
    current = f"{today:%Y-%m}"
    out = []
    for m in months:
        rows = ext[ext["month"] == m]
        dbit, crdt = rows[rows["credit_debit"] == "DBIT"], rows[rows["credit_debit"] == "CRDT"]
        prev_m = str(pd.Period(m, "M") - 1)
        prev = dbit_all[dbit_all["month"] == prev_m]
        partial = m == current
        if partial:
            prev = prev[prev["booking_date"].dt.day <= today.day]
        out.append({"month": m, "partial": partial, "income": r2(crdt["amount"].sum()),
                    "spent": r2(dbit["amount"].sum()), "categories": by_cat(dbit),
                    "compare": {"month": prev_m, "to_day": today.day if partial else None,
                                "spent": r2(prev["amount"].sum()), "categories": by_cat(prev)}})
    return {"months": out}


def transactions(ext: pd.DataFrame) -> list[dict]:
    rows = ext.sort_values("booking_date", ascending=False)
    out = []
    for r in rows.itertuples():
        incoming = r.credit_debit == "CRDT"
        who = r.debtor_name if incoming else r.creditor_name
        out.append({
            "date": f"{r.booking_date:%Y-%m-%d}",
            "amount": r2(r.amount if incoming else -r.amount),
            "category": r.category,
            "who": who.strip() if isinstance(who, str) else "",
            "title": r.remittance_information.strip() if isinstance(r.remittance_information, str) else "",
            "bank": r.bank if isinstance(getattr(r, "bank", None), str) else "",
        })
    return out


def uncategorized(ext: pd.DataFrame) -> list[dict]:
    u = (ext[(ext["category"] == "uncategorized") & (ext["credit_debit"] == "DBIT")]
         .groupby("creditor_name", as_index=False)["amount"].agg(total="sum", count="count")
         .sort_values("total", ascending=False).head(20))
    return [{"who": w, "total": r2(t), "count": int(c)} for w, t, c in zip(u["creditor_name"], u["total"], u["count"])]


def own_accounts() -> set[str]:
    path = DATA_DIR / "own_accounts.csv"
    if not path.exists():
        return set()
    o = pd.read_csv(path, sep=";", dtype=str, comment="#")
    return {i.replace(" ", "").upper() for i in o["iban"].dropna()}


# --- Your own holdings (plugins) ---------------------------------------------------

HOLDINGS_DIR = DATA_DIR / "holdings"
# Colour slots on the page: stocks 1, bonds 2, plugin holdings 3–8 in name
# order (the colour follows the holding, not its size); any more are grey.
SLOTS = 8


def load_plugin_holdings() -> dict[str, tuple[str, pd.DataFrame]]:
    """holdings/<key>.csv → {key: (label, rows by date)}. Each file is one row
    per day, `date;value;profit` (profit = earned so far, so value − profit is
    what went in), with an optional first line `# label: Name`."""
    out = {}
    if not HOLDINGS_DIR.is_dir():
        return out
    for path in sorted(HOLDINGS_DIR.glob("*.csv")):
        key = path.stem.lower()
        if key in ("stocks", "bonds"):
            log(f"{path.name}: name taken by a built-in holding, skipped")
            continue
        with path.open(encoding="utf-8") as f:
            first = f.readline()
        label = (first.split(":", 1)[1].strip() if first.lower().startswith("# label:")
                 else key.replace("_", " ").title())
        try:
            df = pd.read_csv(path, sep=";", comment="#", parse_dates=["date"]).set_index("date").sort_index()
            df = df[["value", "profit"]].astype(float)
        except (ValueError, KeyError) as e:
            log(f"{path.name}: skipped ({e})")
            continue
        if not df.empty:
            out[key] = (label, df)
    return out


def plugin_at(df: pd.DataFrame, day: pd.Timestamp) -> tuple[float, float]:
    """(value, profit) on `day`; before the series starts, its first row
    (nothing earned yet)."""
    row = df.loc[:day].iloc[-1] if day >= df.index[0] else df.iloc[0]
    return float(row["value"]), float(row["profit"])


# --- Assemble ------------------------------------------------------------------

def main() -> int:
    now = pd.Timestamp.now(tz=TZ)
    today = now.tz_localize(None).normalize()

    xtb = load_xtb()
    bonds, cpi_yoy, nbp_rate = load_bonds()
    ext = load_transactions()
    plugins = load_plugin_holdings()

    xtb_by_time = xtb.set_index("captured_at")

    def snapshot(day: pd.Timestamp, moment: pd.Timestamp) -> dict:
        """Value and profit of every holding at `day` (stocks at `moment`)."""
        x = xtb_by_time.loc[:moment].iloc[-1] if moment >= xtb_by_time.index[0] else None
        b = bonds_at(bonds, cpi_yoy, nbp_rate, day)
        return {
            "stocks": (float(x["total_pln"]) if x is not None else 0.0,
                       float(x["profit_pln"]) if x is not None else 0.0),
            "bonds": (float(b["current_value_pln"].sum()), float(b["accrued_pln"].sum())),
            **{key: plugin_at(df, day) for key, (_, df) in plugins.items()},
        }

    snaps = {key: snapshot(today - pd.Timedelta(days=days), now - pd.Timedelta(days=days))
             for key, days in (("now", 0), ("1d", 1), ("7d", 7), ("30d", 30), ("365d", 365))}
    cur = snaps["now"]

    bonds_now = bonds_at(bonds, cpi_yoy, nbp_rate, today)
    xtb_last = xtb.iloc[-1]
    costs = {
        "stocks": float(xtb_last["net_deposits_pln"]),
        "bonds": float(bonds_now["nominal_pln"].sum()) if len(bonds_now) else 0.0,
        **{key: cur[key][0] - cur[key][1] for key in plugins},
    }
    labels = {"stocks": "Stocks", "bonds": "Bonds", **{key: label for key, (label, _) in plugins.items()}}
    slots = {key: i + 1 if i < SLOTS else 0 for i, key in enumerate(labels)}
    # Built-ins first, then your own holdings, largest first.
    order = ["stocks", "bonds", *sorted(plugins, key=lambda k: -cur[k][0])]
    holdings = [{
        "key": key, "label": labels[key], "slot": slots[key],
        "value": r2(cur[key][0]), "profit": r2(cur[key][1]), "cost": r2(costs[key]),
        "profit_pct": r2(cur[key][1] / costs[key] * 100) if costs[key] else 0.0,
    } for key in order]

    changes = {}
    for key in ("1d", "7d", "30d", "365d"):
        then = snaps[key]
        changes[key] = {
            "value": r2(sum(cur[h][0] - then[h][0] for h in labels)),
            "profit": r2(sum(cur[h][1] - then[h][1] for h in labels)),
            "by_holding": {h: r2(cur[h][1] - then[h][1]) for h in labels},
        }

    bonds_list = [{
        "name": r["name"], "type": r.get("series_type", ""),
        "nominal": r2(r["nominal_pln"]), "value": r2(r["current_value_pln"]), "accrued": r2(r["accrued_pln"]),
        "rate": r2(r["current_rate_pct"]), "rate_source": r["rate_source"],
        "purchase": f"{r['purchase_date']:%Y-%m-%d}",
        "maturity": f"{r['maturity_date']:%Y-%m-%d}" if pd.notna(r.get("maturity_date")) else "",
    } for _, r in bonds_now.sort_values("maturity_date").iterrows()]

    tx_mtime = pd.Timestamp((DATA_DIR / "transactions.csv").stat().st_mtime, unit="s", tz="UTC").tz_convert(TZ)
    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "freshness": {
            "stocks": xtb_last["captured_at"].isoformat(timespec="minutes"),
            "banks": tx_mtime.isoformat(timespec="minutes"),
        },
        "net_worth": {
            "value": r2(sum(cur[h][0] for h in labels)),
            "profit": r2(sum(cur[h][1] for h in labels)),
            "cost": r2(sum(costs.values())),
        },
        "holdings": holdings,
        "changes": changes,
        "stocks": stocks_series(xtb),
        "stock_accounts": stock_accounts(),
        "bonds": bonds_list,
        "spending": spending(ext, today),
        "transactions": transactions(ext),
        "uncategorized": uncategorized(ext),
    }

    tmp = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    log(f"net worth {data['net_worth']['value']:,.2f} PLN, {len(data['stocks'])} stock points, "
        f"{len(data['transactions'])} transactions → {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
