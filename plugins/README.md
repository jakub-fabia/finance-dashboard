# Your own holdings (plugins)

Stocks and bonds are built in. Anything else you want in net worth (a savings
account, a deposit, a pension fund, a flat, crypto) is a **plugin**: a script you
drop in this folder. Everything here except this README and `examples/` is
gitignored, so your scripts and the accounts they describe stay private.

## The contract

A plugin is any `*.py` file (run with the image's Python 3.12, with pandas
available) or any other executable file **directly in `plugins/`**. Each run it
writes one file:

```
$DATA_DIR/holdings/<key>.csv
```

```
# label: Savings account
date;value;profit
2026-01-01;10000.00;0.00
2026-01-02;10001.37;1.37
…
```

- **One row per day** (`YYYY-MM-DD`), up to today. Gaps are fine: the dashboard
  uses the latest row on or before each day it needs.
- **`value`**: what the holding is worth that day, in PLN, after any tax you'd
  owe on it.
- **`profit`**: what it has earned so far. `value − profit` is what you put in.
  It drives the day/week/month/year earnings and the profit %, so deposits
  never count as earnings.
- **`# label: …`** (optional first line) is the name on the page. Without it,
  the file name is used: `savings_account` becomes "Savings Account".
- `<key>` is the file name. `stocks` and `bonds` are taken.

Write the file atomically (write `<key>.csv.tmp`, then rename), so the
dashboard never reads half a file. Log to stderr; a non-zero exit is logged and
the other plugins still run. To remove a holding, delete its file from
`holdings/`.

## When plugins run

- right after every bank fetch, so a plugin can read `transactions.csv`;
- on their own schedule, `PLUGINS_CRON_SCHEDULE` (default 00:05 daily);
- on demand: `docker compose run --rm finance-jobs run-plugins`.

The dashboard is rebuilt after each of these. The folder is mounted into the
container, so a new or edited plugin needs no image rebuild.

Plugins see the whole data directory (`DATA_DIR`, `/data` in the container).
Keep any hand-edited inputs there, e.g. `my_savings.csv`, next to the other
data files.

## Transfers to your own accounts

When a plugin's account receives money from your bank account, that transfer
isn't spending. Put the account's IBAN in `$DATA_DIR/own_accounts.csv`:

```
iban;note
PL00 1234 0000 0000 0000 0000 0000;savings account
```

Use an `exclude` rule in `category_rules.csv` instead when the bank shows the
other side by name rather than IBAN.

## Example

`examples/fixed_rate_savings.py` models a savings account from a list of
deposits and a fixed rate, with interest credited monthly and 19% Belka. To
use it, copy it up one level and put your deposits in
`$DATA_DIR/savings_deposits.csv` (format at the top of the script):

```sh
cp plugins/examples/fixed_rate_savings.py plugins/savings.py
docker compose run --rm finance-jobs run-plugins
```
