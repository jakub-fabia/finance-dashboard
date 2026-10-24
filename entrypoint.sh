#!/bin/sh
set -eu

# One-shot modes — useful for ad-hoc runs:
#   docker compose run --rm finance-jobs run-banks   # fetch bank transactions once and exit
#   docker compose run --rm finance-jobs run-cpi     # fetch monthly GUS CPI once and exit
#   docker compose run --rm finance-jobs run-nbp     # fetch NBP reference rate history once and exit
#   docker compose run --rm finance-jobs run-xtb-rebuild  # revalue XTB from the exports in XTB_EXPORT_DIR + Yahoo once and exit
#   docker compose run --rm finance-jobs run-dashboard    # rebuild dashboard.json from the current data once and exit
#
# Every job is followed by build_dashboard.py, so the page always shows the
# latest data (the cron entries below chain it the same way).
DASH='python /app/build_dashboard.py || true'
case "${1:-}" in
    run-banks) python /app/fetch_transactions.py; rc=$?; sh -c "$DASH"; exit $rc ;;
    run-cpi)   python /app/fetch_cpi.py; rc=$?; sh -c "$DASH"; exit $rc ;;
    run-nbp)   python /app/fetch_nbp.py; rc=$?; sh -c "$DASH"; exit $rc ;;
    run-xtb-rebuild) python /app/rebuild_xtb.py; rc=$?; sh -c "$DASH"; exit $rc ;;
    run-dashboard) exec python /app/build_dashboard.py ;;
esac

# Default: long-running supercronic. Schedule env vars may contain multiple
# cron expressions, one per line or separated by ";" — each becomes its own crontab entry running
# the same command.
: >/app/crontab

add_schedules() {
    schedules=$1
    command=$2
    printf '%s\n' "$schedules" | tr ';' '\n' | while IFS= read -r line; do
        trimmed=$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -z "$trimmed" ] && continue
        printf '%s %s\n' "$trimmed" "$command" >>/app/crontab
    done
}

add_schedules "$BANKS_CRON_SCHEDULE" 'cd /app && python /app/fetch_transactions.py; python /app/build_dashboard.py || true'
add_schedules "$CPI_CRON_SCHEDULE"   'cd /app && python /app/fetch_cpi.py; python /app/build_dashboard.py || true'
add_schedules "$NBP_CRON_SCHEDULE"   'cd /app && python /app/fetch_nbp.py; python /app/build_dashboard.py || true'
# XTB value: replay the xStation exports, price the frozen holdings at live
# Yahoo quotes, add bank transfers the export does not have yet.
add_schedules "$XTB_REBUILD_CRON_SCHEDULE" 'cd /app && python /app/rebuild_xtb.py; python /app/build_dashboard.py || true'

echo "scheduling (TZ=${TZ:-UTC}):"
sed 's/^/  /' /app/crontab
exec supercronic /app/crontab
