#!/usr/bin/env python3
"""Fetch the last BANKS_LOOKBACK_DAYS of transactions from every linked bank
and merge them into one CSV.

Each bank has its own Enable Banking application and authorised session,
configured as <BANK>_APP_ID (private key <APP_ID>.pem next to make_jwt.py),
<BANK>_SESSION_ID (reference / renewal) and <BANK>_ACCOUNT_UID (fetched), for
each BANK in BANKS (comma-separated short names of your choice). A bank with
no account UID is skipped, and one bank failing (HTTP 429, expired session)
doesn't stop the others — the run exits non-zero after writing whatever did
arrive.

Single file, semicolon-separated (project convention — matches cpi.csv,
nbp_rates.csv, xtb_rebuilt.csv). Rows carry a `bank` column; re-runs are
idempotent: rows already present (matched by bank + transaction_id) are
skipped, so it's safe to fire daily.

Output rows are sorted by booking_date descending; write is atomic
(tmp → replace).
"""
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = Path(os.environ.get("ENV_FILE", ROOT / ".env"))
SCRIPT_PY = ROOT / "make_jwt.py"
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", ROOT / "transactions" / "transactions.csv"))
LOOKBACK_DAYS = int(os.environ.get("BANKS_LOOKBACK_DAYS", "30"))
API_BASE = os.environ.get("API_BASE", "https://api.enablebanking.com")

HEADER = [
    "booking_date", "credit_debit", "amount", "currency",
    "creditor_name", "debtor_name", "remittance_information",
    "creditor_iban", "debtor_iban", "transaction_id", "bank",
]


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_jwt(env_vars: dict[str, str], app_id: str) -> str:
    child_env = os.environ.copy()
    for k, v in env_vars.items():
        child_env.setdefault(k, v)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PY), app_id],
        capture_output=True, text=True, check=True, cwd=ROOT, env=child_env,
    )
    return result.stdout.strip()


def fetch_transactions(account_uid: str, jwt: str, date_from: str, date_to: str) -> list[dict]:
    transactions: list[dict] = []
    continuation_key = None
    while True:
        params = {"date_from": date_from, "date_to": date_to}
        if continuation_key:
            params["continuation_key"] = continuation_key
        url = f"{API_BASE}/accounts/{account_uid}/transactions?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {jwt}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        transactions.extend(data.get("transactions", []))
        continuation_key = data.get("continuation_key")
        if not continuation_key:
            break
    return transactions


def to_row(tx: dict, bank: str) -> dict[str, str]:
    """Flatten an Enable Banking transaction into a CSV row (str-typed)."""
    amt = tx.get("transaction_amount") or {}
    creditor = tx.get("creditor") or {}
    debtor = tx.get("debtor") or {}
    creditor_acc = tx.get("creditor_account") or {}
    debtor_acc = tx.get("debtor_account") or {}
    remittance = tx.get("remittance_information") or []
    amount_raw = amt.get("amount")
    try:
        amount_str = f"{float(amount_raw):g}" if amount_raw is not None else ""
    except (TypeError, ValueError):
        amount_str = str(amount_raw) if amount_raw is not None else ""
    return {
        "booking_date":           tx.get("booking_date") or "",
        "credit_debit":           tx.get("credit_debit_indicator") or "",
        "amount":                 amount_str,
        "currency":               amt.get("currency") or "",
        "creditor_name":          creditor.get("name") or "",
        "debtor_name":            debtor.get("name") or "",
        "remittance_information": " | ".join(s for s in remittance if s),
        "creditor_iban":          (creditor_acc or {}).get("iban") or "",
        "debtor_iban":            (debtor_acc or {}).get("iban") or "",
        "transaction_id":         tx.get("transaction_id") or "",
        "bank":                   bank,
    }


def load_existing(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    return rows


def write_atomic(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def main() -> int:
    env_vars = load_env(ENV_FILE)

    def setting(name: str) -> str:
        return (env_vars.get(name) or os.environ.get(name) or "").strip()

    # BANKS=MAIN,SECOND — your own short names: the env prefix of each bank's
    # settings, and (lowercased) the `bank` column.
    banks = [b.strip().upper() for b in setting("BANKS").split(",") if b.strip()]
    accounts = [(b.lower(), setting(f"{b}_APP_ID"), setting(f"{b}_ACCOUNT_UID")) for b in banks]
    accounts = [(bank, app, uid) for bank, app, uid in accounts if uid]
    if not accounts:
        print("no bank account configured (set BANKS and <NAME>_ACCOUNT_UID in .env)", file=sys.stderr)
        return 1

    today = date.today()
    date_to = today.isoformat()
    date_from = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()

    existing = load_existing(OUTPUT_PATH)
    seen = {(r["bank"], r["transaction_id"]) for r in existing if r.get("transaction_id")}

    new_rows: list[dict] = []
    failed: list[str] = []
    for bank, app_id, uid in accounts:
        if not app_id:
            print(f"[{bank}] {bank.upper()}_APP_ID missing", file=sys.stderr, flush=True)
            failed.append(bank)
            continue
        try:
            jwt = get_jwt(env_vars, app_id)
            transactions = fetch_transactions(uid, jwt, date_from, date_to)
        except subprocess.CalledProcessError as e:
            print(f"[{bank}] JWT failed (missing {app_id}.pem?): {e.stderr.strip()[-200:]}",
                  file=sys.stderr, flush=True)
            failed.append(bank)
            continue
        except urllib.error.HTTPError as e:
            # 429 = PSD2 daily quota (~4/account/day); 401/403 = session expired.
            detail = e.read().decode(errors="replace")[:200]
            print(f"[{bank}] HTTP {e.code}: {detail}", file=sys.stderr, flush=True)
            failed.append(bank)
            continue
        added = 0
        for tx in transactions:
            row = to_row(tx, bank)
            key = (bank, row["transaction_id"])
            if not row["transaction_id"] or key in seen:
                continue
            new_rows.append(row)
            seen.add(key)
            added += 1
        print(f"[{bank}] [{date_from}..{date_to}] fetched={len(transactions)} new={added}", flush=True)

    combined = existing + new_rows
    # Newest first.
    combined.sort(key=lambda r: r.get("booking_date") or "", reverse=True)
    write_atomic(OUTPUT_PATH, combined)

    print(f"new={len(new_rows)} total={len(combined)} -> {OUTPUT_PATH}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
