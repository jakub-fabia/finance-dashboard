# One image, several small cron jobs under supercronic:
#   - banks:        bank transactions via Enable Banking (PyJWT + cryptography)
#   - xtb-rebuild:  XTB value from xStation exports + Yahoo prices (openpyxl)
#   - gus-cpi / nbp-rates: public statistics (stdlib)
#   - dashboard:    precomputes dashboard.json for the static page (pandas)
FROM python:3.12.7-slim-bookworm

ARG SUPERCRONIC_VERSION=v0.2.33
ARG TARGETARCH
# Build-time only — keeps tzdata's debconf prompt from hanging the build.
# Does not leak into runtime env (ARG, not ENV).
ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    TZ=Europe/Warsaw \
    \
    BANKS_CRON_SCHEDULE="0 6 * * *" \
    CPI_CRON_SCHEDULE="0 6 20 * *" \
    NBP_CRON_SCHEDULE="0 7 * * 1" \
    XTB_REBUILD_CRON_SCHEDULE="2,17,32,47 9-17 * * 1-5;10 18,23 * * 1-5" \
    PLUGINS_CRON_SCHEDULE="5 0 * * *" \
    \
    OUTPUT_PATH=/data/transactions.csv \
    XTB_EXPORT_DIR=/data/XTB_exports \
    XTB_REBUILT_FILE=/data/xtb_rebuilt.csv \
    BANKS_LOOKBACK_DAYS=35

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
 && curl -fsSL \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH:-amd64}" \
      -o /usr/local/bin/supercronic \
 && chmod +x /usr/local/bin/supercronic \
 && apt-get purge -y curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      pyjwt==2.12.1 \
      cryptography==48.0.0 \
      openpyxl==3.1.5 \
      numpy==2.1.3 \
      pandas==2.2.3

WORKDIR /app

# Bank-fetch scripts + Enable Banking signing keys. Credentials
# (<BANK>_APP_ID, <BANK>_ACCOUNT_UID) come from the container env via the
# compose env_file. The keys are baked in: each bank's is <APP_ID>.pem,
# looked up at runtime (none yet is fine — the bank job just reports it).
COPY banks/fetch_transactions.py banks/make_jwt.py banks/authorize.py banks/*.pem* ./
COPY xtb/rebuild_xtb.py ./
COPY gus-cpi/fetch_cpi.py ./
COPY nbp-rates/fetch_nbp.py ./
COPY dashboard/build_dashboard.py ./
COPY entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh

VOLUME ["/data"]

ENTRYPOINT ["/app/entrypoint.sh"]
