#!/usr/bin/env python3
"""Authorise one bank in Enable Banking → session id + account UID for .env.

Usage (interactive, needs a browser for the bank login):
  docker compose run --rm -it --entrypoint python finance-jobs /app/authorize.py MAIN
Two-step (no terminal needed — e.g. driven by someone else):
  … authorize.py MAIN                        # prints the link, exits when stdin isn't a TTY
  … authorize.py MAIN --code '<redirect URL or code>'   # finishes it

Reads <BANK>_APP_ID (private key <APP_ID>.pem next to make_jwt.py) and
<BANK>_ASPSP (the bank's name as Enable Banking lists it; run without it to see
the list), finds the bank in Enable Banking's Polish ASPSP list, starts an authorisation with the
longest consent the bank allows, and prints the link. Log in at the bank,
approve, and paste back the URL you were redirected to (or just its `code`).
Prints <BANK>_SESSION_ID / <BANK>_ACCOUNT_UID lines to put in .env.

Also used to renew an expiring session (same command, new ids). Metadata
calls only — doesn't touch the ~4/day transaction quota.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = os.environ.get("API_BASE", "https://api.enablebanking.com")
ROOT = Path(__file__).resolve().parent


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def call(method: str, path: str, jwt: str, body: dict | None = None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        die(f"{method} {path} → HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")


def code_from(pasted: str) -> str:
    pasted = pasted.strip()
    return urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query).get("code", [pasted])[0]


def main() -> None:
    args = sys.argv[1:]
    code = None
    if len(args) == 3 and args[1] == "--code":
        code = code_from(args[2])
        args = args[:1]
    if len(args) != 1:
        die("usage: authorize.py BANK [--code URL_OR_CODE]   (BANK = a name from BANKS in .env)")
    bank = args[0].upper()
    # How the bank is named in Enable Banking's ASPSP list (matched case-insensitively).
    aspsp_name = os.environ.get(f"{bank}_ASPSP", "").strip()
    app_id = os.environ.get(f"{bank}_APP_ID", "").strip()
    if not app_id:
        die(f"{bank}_APP_ID is not set")
    if not (ROOT / f"{app_id}.pem").exists():
        die(f"private key {app_id}.pem not found in {ROOT} — add it to banks/ and rebuild")
    jwt = subprocess.run([sys.executable, str(ROOT / "make_jwt.py"), app_id],
                         capture_output=True, text=True, check=True).stdout.strip()
    if code:
        finish(bank, jwt, code)
        return

    app = call("GET", "/application", jwt)
    redirects = app.get("redirect_urls") or []
    if not redirects:
        die("the application has no redirect URL — add one in the Enable Banking panel")
    print(f"app: {app.get('name')} ({app.get('environment')}), redirect {redirects[0]}")

    aspsps = call("GET", "/aspsps?country=PL", jwt).get("aspsps", [])
    matches = [a for a in aspsps if aspsp_name and aspsp_name.lower() in a["name"].lower()]
    if not matches:
        die(f"set {bank}_ASPSP to one of the banks Enable Banking lists for PL"
            f"{f' (nothing matches {aspsp_name!r})' if aspsp_name else ''}: "
            + ", ".join(sorted(a["name"] for a in aspsps)))
    # Prefer the personal (retail) flavour when the bank lists several.
    aspsp = next((a for a in matches if "personal" in (a.get("psu_types") or [])), matches[0])
    max_secs = aspsp.get("maximum_consent_validity") or 90 * 86400
    valid_until = datetime.now(timezone.utc) + timedelta(seconds=max_secs) - timedelta(minutes=5)
    print(f"bank: {aspsp['name']} — consent valid until {valid_until:%Y-%m-%d}")

    auth = call("POST", "/auth", jwt, {
        "access": {"valid_until": valid_until.isoformat()},
        "aspsp": {"name": aspsp["name"], "country": "PL"},
        "state": str(uuid.uuid4()),
        "redirect_url": redirects[0],
        "psu_type": "personal",
    })
    print("\n1. Open this link, log in to the bank and approve access:\n")
    print("   " + auth["url"] + "\n")
    print("2. You'll land on the redirect page (it may show an error — that's fine).")
    if not sys.stdin.isatty():
        print(f"   Then run: authorize.py {bank} --code '<that full URL>'")
        return
    code = code_from(input("   Paste that full URL (or just the code) here: "))
    if not code:
        die("no code found")
    finish(bank, jwt, code)


def finish(bank: str, jwt: str, code: str) -> None:
    sess = call("POST", "/sessions", jwt, {"code": code})
    accounts = sess.get("accounts") or []
    print(f"\nsession authorised, valid until {(sess.get('access') or {}).get('valid_until')}")
    print("\nPut these in .env, then `docker compose up -d finance-jobs`:\n")
    print(f"{bank}_SESSION_ID={sess['session_id']}")
    for i, acc in enumerate(accounts):
        uid = acc.get("uid") if isinstance(acc, dict) else acc
        iban = (acc.get("account_id") or {}).get("iban") if isinstance(acc, dict) else None
        name = acc.get("name") if isinstance(acc, dict) else None
        prefix = "" if i == 0 else "# other account: "
        print(f"{prefix}{bank}_ACCOUNT_UID={uid}" + (f"   # {name or ''} {iban or ''}".rstrip() if (name or iban) else ""))


if __name__ == "__main__":
    main()
