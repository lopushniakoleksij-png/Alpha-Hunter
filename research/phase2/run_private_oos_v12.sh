#!/usr/bin/env bash
# Alpha Hunter — isolated, resumable OOS V1.2 read-only evidence certification.
# Does NOT modify V1.0/V1.1 source files/certificates or app/production state.
set -euo pipefail
umask 077
BASE="$HOME/.alpha-hunter-phase2-private"
R="$BASE/research/phase2"
MARKET="$BASE/oos-v12-20261020-21-23-market"
SNAPSHOT="$BASE/oos-v12-20261020-21-23-signals.csv"
CERT="$BASE/oos-v12-20261020-21-23-certificate"
DRIVER="$BASE/.pilot-export-venv/bin/python"
OLD_CANDLE="$BASE/pilot-48h-20261108-recapture"
OLD_SIGNAL="$BASE/pilot_signals_20261108_verified.csv"
OLD_CERT="$BASE/pilot-certificate-20261108/certificate.json"
OLD_V11="$BASE/pilot-v11-independent-20261108/v11_independent_research.json"

cd "$R"
if [[ ! -f "$OLD_CANDLE/manifest.json" || ! -f "$OLD_SIGNAL" ||
      ! -f "$OLD_CERT" || ! -f "$OLD_V11" ]]; then
  echo "ERROR: Protected V1.0/V1.1 evidence missing; no research execution." >&2
  exit 1
fi
if [[ ! -x "$DRIVER" ]]; then
  echo "ERROR: Existing isolated private psycopg Python driver missing. No install attempted." >&2
  exit 1
fi
# Validate original source hashes & snapshot. This only reads protected files.
python - <<'PY'
from pathlib import Path
from phase2_pilot_offline_certify import validate_sources,validate_signals
base=Path.home()/".alpha-hunter-phase2-private"
raw,manifest=validate_sources(base/"pilot-48h-20261108-recapture")
rows,digest=validate_signals(base/"pilot_signals_20261108_verified.csv")
assert len(raw)==3 and len(rows)==175
print("PROTECTED V1.0 SOURCE HASHES: PASS | 3 market responses, 175 signals")
PY
# Detect accidental mutation of key sealed artifacts, checking before and after.
FROZEN_BEFORE="$(sha256sum "$OLD_CANDLE/manifest.json" "$OLD_SIGNAL" "$OLD_CERT" "$OLD_V11")"

echo "OOS V1.2 predeclared dates: 20/21/23 Oct 2026 UTC; BTC/ETH/SOL only."
python -m unittest -q test_phase2_oos_v12

if [[ -f "$MARKET/manifest.json" ]]; then
  echo "Existing new V1.2 private raw archive found: VERIFYING, not overwriting."
  python - <<'PY'
from pathlib import Path
from phase2_oos_v12_replay import checked_archive
base=Path.home()/".alpha-hunter-phase2-private"
raw,manifest=checked_archive(base/"oos-v12-20261020-21-23-market")
print("OOS V1.2 raw source hashes: PASS",len(raw))
PY
elif [[ -e "$MARKET" ]]; then
  echo "ERROR: Partial V1.2 market source directory found; refuse overwrite." >&2
  exit 1
else
  python phase2_oos_v12_capture.py --out "$MARKET"
fi

if [[ -f "$SNAPSHOT" && ! -L "$SNAPSHOT" ]]; then
  echo "Existing V1.2 snapshot: VALIDATING, not overwriting."
  python - <<'PY'
from pathlib import Path
from phase2_oos_v12_export import inspect_export
base=Path.home()/".alpha-hunter-phase2-private"
print("OOS V1.2 450-row cohort:",inspect_export(base/"oos-v12-20261020-21-23-signals.csv"))
PY
elif [[ -e "$SNAPSHOT" || -L "$SNAPSHOT" ]]; then
  echo "ERROR: Unexpected snapshot path; no overwrite." >&2
  exit 1
else
  echo "Read-only SQL export requires existing Supabase database password (hidden)."
  "$DRIVER" phase2_oos_v12_export.py --out "$SNAPSHOT"
fi

if [[ -e "$CERT" || -L "$CERT" ]]; then
  echo "ERROR: V1.2 certificate path already exists; do not overwrite." >&2
  exit 1
fi
python phase2_oos_v12_replay.py --archive "$MARKET" \
  --signals "$SNAPSHOT" --out "$CERT"

FROZEN_AFTER="$(sha256sum "$OLD_CANDLE/manifest.json" "$OLD_SIGNAL" "$OLD_CERT" "$OLD_V11")"
if [[ "$FROZEN_BEFORE" != "$FROZEN_AFTER" ]]; then
  echo "CRITICAL: sealed V1.0/V1.1 hash changed; STOP and investigate." >&2
  exit 1
fi
echo "PROTECTED V1.0/V1.1 FILE HASHES: UNCHANGED"
echo "OOS V1.2 PRIVATE REPLAY: completed, research only, no trading authority."
