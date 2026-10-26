# Setting it up

Everything lives in one data directory (`FINANCE_DATA_DIR` in `.env`, mounted
at `/data`). The jobs write their CSVs there, you keep a few hand-edited files
there, and the dashboard reads `dashboard.json` from it. CSVs use `;` as the
separator.

| File in the data directory | Written by | You edit it? |
|---|---|---|
| `transactions.csv` | bank job | no |
| `XTB_exports/*.xlsx` | you (xStation export) | drop files in |
| `xtb_rebuilt.csv`, `xtb_holdings.csv` | XTB job | no |
| `bonds.csv` | you | yes |
| `cpi.csv`, `nbp_rates.csv` | CPI / NBP jobs | no |
| `category_rules.csv`, `tx_overrides.csv` | you | yes |
| `own_accounts.csv` | you (optional) | yes |
| `yahoo_overrides.csv` | you (optional) | yes |
| `holdings/*.csv` | your plugins | no |
| `dashboard.json` | dashboard builder (after every job) | no |

Every source is optional: a holding with no data shows as 0, and spending is
empty without bank data.

## 1. Basics

```sh
git clone https://github.com/<you>/finance-dashboard && cd finance-dashboard
cp .env.example .env              # set FINANCE_DATA_DIR to where your data should live
mkdir -p "$(grep ^FINANCE_DATA_DIR .env | cut -d= -f2)/XTB_exports"
docker compose build
docker compose run --rm finance-jobs run-cpi
docker compose run --rm finance-jobs run-nbp
docker compose up -d              # jobs on their schedules + the page on :2718
```

`docker compose logs finance-jobs` shows the schedule it installed and each
job's output.

## 2. Bank transactions (Enable Banking)

[Enable Banking](https://enablebanking.com) is a licensed PSD2 aggregator. In
"restricted" mode a production application works without a contract, for
accounts you link yourself. That's what this uses, for any number of banks.

In `.env`, list your banks under short names of your choice, for example
`BANKS=MAIN,SECOND`. Each name is the prefix of that bank's settings
(`MAIN_ASPSP`, `MAIN_APP_ID`, `MAIN_SESSION_ID`, `MAIN_ACCOUNT_UID`) and, in
lowercase, the `bank` column of `transactions.csv`.

For each bank:

1. **Register an application** in the Enable Banking Control Panel
   (Applications → register). Choose the **production** environment and add a
   redirect URL: any https page works, since you only copy the URL you land on.
   Let the panel generate the key pair. The private key downloads as
   `<application id>.pem`.
2. **Activate it for your own accounts.** The panel offers to activate a
   restricted application by linking your accounts. Follow it for this bank.
   The screens may change, so check Enable Banking's docs if it looks different.
3. **Install the key.** Put the `.pem` in `banks/` (it's gitignored, and baked
   into the image at build time). Set `<BANK>_APP_ID=<application id>` in `.env`,
   and `<BANK>_ASPSP` to the bank's name as Enable Banking lists it (a part of
   the name is enough). Then run `docker compose build`. If you leave
   `<BANK>_ASPSP` empty, step 4 prints the list of Polish banks to pick from.
4. **Authorise:**
   ```sh
   docker compose run --rm -it --entrypoint python finance-jobs /app/authorize.py MAIN
   ```
   Open the link, log in to the bank and approve. Paste back the URL you were
   redirected to (an error page there is fine). It prints `MAIN_SESSION_ID=…`
   and `MAIN_ACCOUNT_UID=…`: put them in `.env`.
5. **Fetch:** `docker compose up -d` (to pick up `.env`), then
   `docker compose run --rm finance-jobs run-banks`.

Things to know:

- **The consent expires.** The script asks for the longest the bank allows,
  usually 90–180 days. When fetches start failing with 401/403, run step 4
  again. It uses no transaction quota.
- **Rate limit:** PSD2 allows about 4 automatic fetches per account per day.
  The default `BANKS_CRON_SCHEDULE` in `.env.example` fetches once a day.
- **Overlap:** each run fetches the last `BANKS_LOOKBACK_DAYS` (keep it ≥ 15)
  and de-duplicates by bank + transaction id. Banks add backdated rows, and the
  overlap is what catches them.
- **Transfers between your own accounts** (same name on both sides, a
  counterparty IBAN that is one of yours, or a bank "own transfer") are left
  out of spending and income automatically.

## 3. XTB (stocks and ETFs)

XTB has no API for this, so the job replays XTB's own account-history export.
The "Cash Operations" sheet is a complete ledger: deposits, withdrawals,
every buy and sell with quantity and price, dividends, taxes and IKE transfers.
From that it rebuilds cash and holdings for any moment and prices them with
Yahoo Finance. Prices come every 15 minutes for the last 60 days, hourly
before that, and from daily closes where needed. FX comes from Yahoo, with NBP
filling older dates.

**Export** (repeat after you buy or sell):

1. In xStation 5, open **History** for one account and set the date range
   from the account's opening to today.
2. **Export** it as Excel. Do this for every account you have: the main PLN
   account, IKE/IKZE, and the EUR and USD sub-accounts.
3. Put the `.xlsx` files in `XTB_exports/`, named like XTB names them:
   `<PLN|EUR|USD|IKE>_<account number>_<from>_<to>.xlsx`. The prefix tells the
   job the account's currency, and `IKE` means a PLN-denominated IKE. Older
   exports can stay: operations are de-duplicated by ID.
4. Run `docker compose run --rm finance-jobs run-xtb-rebuild`, or wait for
   the next scheduled run.

Notes:

- **Between exports** the job keeps the holdings frozen at the last export and
  prices them live. Transfers between your bank and XTB after the export are
  picked up from bank transactions mentioning `XTB` / `X-TRADE`. They are
  added as cash (to `XTB_PENDING_ACCOUNT`, default the `PLN_…` account) and as
  deposits, so value moves but profit doesn't. **Trades after the export stay
  invisible until the next export.**
- **Profit** is all-time: value minus net deposits (each converted to PLN on
  the day it moved). The stocks breakdown splits it into open positions
  (average cost) and "Sold positions, dividends, fees".
- **Symbols:** XTB's suffix maps to Yahoo's (`YAHOO_SUFFIX`), with
  `YAHOO_OVERRIDE` for instruments Yahoo lists under a different code. Each run
  compares XTB's fill prices with Yahoo and logs `CHECK MAPPING` when a ticker
  is more than 3% off. Add an override when you see it, or when the run stops
  with "Yahoo has no …": a row `xtb_ticker;yahoo_symbol` in
  `yahoo_overrides.csv` (header included), e.g. `ABCD.DE;WXYZ.DE`. Keeping
  them there rather than in the code keeps your tickers out of git.
- Positions in a currency other than the account's are valued at market
  −0.5%, matching XTB's conversion fee. CFDs only count realised cash.
- Every run recomputes the whole history (a few Yahoo requests per
  instrument you ever held; well under a minute). The default schedule is every 15 minutes during the Warsaw session
  plus 18:10 and 23:10, Monday to Friday.

## 4. Treasury bonds

Keep one row per purchase in `bonds.csv`:

```
name;nominal_pln;first_period_rate;margin
EDO0337/9;2500;0.0680;0.0175
TOS0629/14;1000;0.0580
```

- **`name`** is the series code: type + maturity `MMYY`, plus an optional
  `/DD` for the day you bought it. `EDO0337/9` is an EDO maturing in March 2037,
  bought on the 9th. The type sets the defaults: duration, interest period,
  compounding, and which index drives later periods. Supported types are OTS,
  ROR, DOR, TOS, COI, EDO, ROS and ROD.
- **`nominal_pln`** is what you paid.
- **`first_period_rate`** is the first year's rate as a decimal.
- **`margin`** applies only to indexed series (EDO, COI, ROS, ROD, ROR, DOR).
  Later periods use CPI y/y from 2 months before the period starts (NBP
  reference rate for ROR/DOR), plus the margin. Leave it empty for fixed-rate
  series (TOS, OTS).
- Optional extra columns override the defaults:
  `purchase_date;period_months;compounding;cpi_lookback_months;rate_index`.
  Short rows are fine.

Accrual walks each bond period by period from its purchase date. Compounding
series roll each completed year's interest into principal; the others pay it
out. Values are before the 19% Belka tax.

CPI (GUS) and the NBP rate are fetched by their own jobs: monthly and weekly
by default, or `run-cpi` / `run-nbp`. `CPI_START_YEAR` must cover your oldest
indexed bond.

## 5. Your own holdings (plugins)

Savings accounts, deposits, pension funds or anything else you want in net
worth: write a small script that outputs one CSV per holding
(`date;value;profit`, one row per day) and put it in `plugins/`. It runs
after every bank fetch and daily, and each file becomes a row next to Stocks
and Bonds. Your scripts are gitignored. The contract and a ready-made example
(a fixed-rate savings account) are in **[plugins/README.md](../plugins/README.md)**.

## 6. Spending categories

`category_rules.csv` sorts bank transactions. The first matching row wins:

```
category;field;pattern
exclude;*;\bXTB\b|MY SAVINGS BANK
groceries;creditor_name;BIEDRONKA|LIDL|ZABKA
rent;remittance_information;\bCZYNSZ\b
salary;debtor_name;MY EMPLOYER
```

- `pattern` is a case-insensitive regular expression with no `;` inside it.
- `field` is `creditor_name`, `debtor_name`, `remittance_information`, or `*`
  for any of the three.
- **`exclude`** drops the row from spending and income entirely. Use it for
  money moving to your investments (broker, savings accounts, funds). Exclude rows
  are checked before all other rules.
- Anything unmatched is `uncategorized`. The dashboard lists the top
  uncategorised merchants so you can write rules for them.
- `tx_overrides.csv` (`transaction_id;category`) pins single transactions,
  for merchants that can't be told apart by a rule.

These category names get fixed colours on the page: rent, groceries, eatout,
leisure, transportation, subscriptions, shopping and travel (`CAT_SLOTS` in
`dashboard/web/app.js`). Any other category is grey.

After editing either file:
`docker compose run --rm finance-jobs run-dashboard`.

## 7. Day to day

- **Page:** `http://<server>:2718`. Add it to your phone's home screen.
  Footer dates show when each source last updated, and a dashed underline
  means a job is overdue.
- **After trading on XTB:** export again (section 3).
- **Every few months:** renew the bank consent (section 2, step 4).
- **One-off runs:** `docker compose run --rm finance-jobs <mode>`, where mode is
  `run-banks`, `run-xtb-rebuild`, `run-cpi`, `run-nbp`, `run-plugins` or
  `run-dashboard`. Each job is followed by a dashboard rebuild.
- **Schedules:** `*_CRON_SCHEDULE` variables in `.env`, Europe/Warsaw time.
  Separate several cron expressions with `;`.
- **Upgrading:** `git pull && docker compose build && docker compose up -d`.
  Page-only changes (`dashboard/web/`) are live on reload.
