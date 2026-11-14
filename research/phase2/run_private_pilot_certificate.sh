#!/usr/bin/env bash
# Alpha Hunter Phase 2 — psql-free, private, read-only 175-signal export and replay.
# Isolated Python driver under private QA; no app dependency or production changes.
set -euo pipefail
umask 077

BASE="$HOME/.alpha-hunter-phase2-private"
RESEARCH="$BASE/research/phase2"
ARCHIVE="$BASE/pilot-48h-20261108-recapture"
SIGNALS="$BASE/pilot_signals_20261108_verified.csv"
CERT="$BASE/pilot-certificate-20261108"
DRIVER_ENV="$BASE/.pilot-export-venv"
cd "$RESEARCH"

if [[ ! -f "$ARCHIVE/manifest.json" ]]; then
  echo "ERROR: Prior private 3-response candle capture missing. No export attempted." >&2
  exit 1
fi
if [[ -e "$SIGNALS" || -e "$CERT" ]]; then
  echo "ERROR: Verified signals or certificate destination already exists; refusing overwrite." >&2
  exit 1
fi

# Validate immutable source evidence before connecting to the database.
python - <<'PY'
from pathlib import Path
from phase2_pilot_offline_certify import validate_sources
folder=Path.home()/".alpha-hunter-phase2-private/pilot-48h-20261108-recapture"
raw,_=validate_sources(folder)
print("PRIVATE 48H CANDLE HASHES: PASS (" + ", ".join(sorted(raw)) + ")")
PY

# psycopg is installed only into an isolated venv inside private QA.
# The active Alpha Hunter repair .venv, Git branch and production are untouched.
if [[ ! -x "$DRIVER_ENV/bin/python" ]]; then
  echo "Preparing isolated private PostgreSQL read-only export environment."
  python -m venv "$DRIVER_ENV"
fi
if ! "$DRIVER_ENV/bin/python" -c 'import psycopg' >/dev/null 2>&1; then
  echo "Installing pinned psycopg v3 driver only inside the private QA environment."
  "$DRIVER_ENV/bin/python" -m pip install --disable-pip-version-check --no-input 'psycopg[binary]==3.3.9'
fi

echo "Exporting the exact frozen 175-signal cohort via a READ ONLY transaction."
echo "You may be asked for your existing Supabase database password; type it only in the terminal."
"$DRIVER_ENV/bin/python" "$RESEARCH/phase2_pilot_signal_export.py" --out "$SIGNALS"

# This will fail if the private export is incomplete or differs from observed
# conservative pilot outcomes. No fabricated certificate on discrepancy.
python "$RESEARCH/phase2_pilot_offline_certify.py" \
  --archive "$ARCHIVE" \
  --signals "$SIGNALS" \
  --out "$CERT"

echo "RESEARCH PILOT: private evidence certificate written, no trading authority."
