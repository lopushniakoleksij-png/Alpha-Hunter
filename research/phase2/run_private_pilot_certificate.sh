#!/usr/bin/env bash
# Alpha Hunter Phase 2 — single-step, read-only private cohort export/replay.
# NO trading, production DDL/DML, deployment, Git switch, or credentials on disk.
set -euo pipefail
umask 077

BASE="$HOME/.alpha-hunter-phase2-private"
RESEARCH="$BASE/research/phase2"
ARCHIVE="$BASE/pilot-48h-20261108-recapture"
SIGNALS="$BASE/pilot_signals_20261108_verified.csv"
CERT="$BASE/pilot-certificate-20261108"
TMP=""

cleanup() { if [[ -n "$TMP" && -e "$TMP" ]]; then rm -f -- "$TMP"; fi; }
trap cleanup EXIT

cd "$RESEARCH"
if [[ ! -f "$ARCHIVE/manifest.json" ]]; then
  echo "ERROR: Prior private 3-response capture is missing. No export attempted." >&2
  exit 1
fi
if [[ -e "$SIGNALS" || -e "$CERT" ]]; then
  echo "ERROR: Existing signal export or certificate found. Refusing to overwrite private evidence." >&2
  exit 1
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is unavailable in this Codespace. No export attempted." >&2
  exit 1
fi
if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: Python unavailable in this Codespace." >&2
  exit 1
fi

# Fail closed before requesting a database password if previously captured
# candles have been modified or source URL scope is incorrect.
python - <<'PY'
from pathlib import Path
from phase2_pilot_offline_certify import validate_sources
folder=Path.home()/".alpha-hunter-phase2-private/pilot-48h-20261108-recapture"
raw,_=validate_sources(folder)
print("PRIVATE 48H CANDLE HASHES: PASS (" + ", ".join(sorted(raw)) + ")")
PY

TMP="$(mktemp "$BASE/.pilot_signals_20261108.XXXXXX.csv")"
echo "Exporting 175 read-only signal rows to a private CSV."
echo "psql may ask for the existing Supabase database password. Type it in the terminal only."
PGSSLMODE=require psql \
  -h aws-0-eu-west-1.pooler.supabase.com \
  -p 5432 \
  -U postgres.yjgtjzymfurqzqqxcrnp \
  -d postgres -W -X -q --single-transaction \
  -v ON_ERROR_STOP=1 \
  -c "SET TRANSACTION READ ONLY" \
  -c "COPY (
    SELECT signal_id, symbol, detected_at_utc, created_at,
           state, direction, trade_permission, entry_price,
           stop_loss, take_profit, reference_price,
           huge_rr_score, confidence_estimate_pct, reward_risk
    FROM public.alpha_hunter_signals
    WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
      AND detected_at_utc >= '2026-11-08T00:00:00Z'
      AND detected_at_utc < '2026-11-09T00:00:00Z'
    ORDER BY symbol, detected_at_utc, signal_id
  ) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)" > "$TMP"

# Read-only validation in a separate offline process; empty, partial, duplicate,
# incorrectly scoped or unblocked snapshots are rejected before renaming.
python - "$TMP" <<'PY'
import sys
from pathlib import Path
from phase2_pilot_offline_certify import validate_signals
rows, sha256=validate_signals(Path(sys.argv[1]))
print(f"PRIVATE 175-ROW SIGNAL SNAPSHOT: PASS | rows={len(rows)} | sha256={sha256}")
PY

if [[ -e "$SIGNALS" ]]; then
  echo "ERROR: Private destination appeared during export; refusing overwrite." >&2
  exit 1
fi
mv -- "$TMP" "$SIGNALS"
TMP=""
python phase2_pilot_offline_certify.py \
  --archive "$ARCHIVE" \
  --signals "$SIGNALS" \
  --out "$CERT"

echo "NOTE: Certificate covers reproducible historical research, NOT actual fills or live trading."
