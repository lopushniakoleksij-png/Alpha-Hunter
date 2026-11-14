#!/usr/bin/env bash
# Alpha Hunter P0: GitHub Actions ephemeral PostgreSQL 17 ONLY.
# No real DB endpoints, secrets, external services or production writes.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true"
   || "${GITHUB_REF_NAME:-}" != "fix/supabase-write-timeout-qa"
   || "${PGHOST:-}" != "127.0.0.1"
   || "${PGDATABASE:-}" != "isolated_atomic_scan_qa"
   || "${PGUSER:-}" != "postgres" ]]; then
  echo "REFUSED: real statement-timeout QA requires disposable CI PostgreSQL 17 only" >&2
  exit 2
fi

psql -X -v ON_ERROR_STOP=1 \
  -f ops/sql/qa_atomic_core_scan_real_timeout_setup_v01.sql

# The 61st child's AFTER INSERT trigger sleeps for 600ms, while PostgreSQL
# enforces 200ms for the complete RPC SQL statement. This is genuine
# statement_timeout cancellation, not an injected RAISE EXCEPTION.
tmp_log="$(mktemp)"
trap 'rm -f "$tmp_log"' EXIT

set +e
PGOPTIONS="-c statement_timeout=200ms" \
  psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -At \
  -c "SELECT public.alpha_hunter_commit_core_scan_v01(parent_rows,children_rows,signals_rows,features_rows,readiness_rows) FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_REAL_TIMEOUT';" \
  >"$tmp_log" 2>&1
status="$?"
set -e

if [[ "$status" -eq 0 ]]; then
  echo "FAIL: 61-symbol candidate unexpectedly committed despite 200ms PostgreSQL timeout" >&2
  cat "$tmp_log" >&2
  exit 1
fi
if ! grep -Fq "57014" "$tmp_log" \
   || ! grep -Fq "canceling statement due to statement timeout" "$tmp_log"; then
  echo "FAIL: SQL request failed for a reason other than PostgreSQL statement_timeout" >&2
  cat "$tmp_log" >&2
  exit 1
fi
echo "PASS: PostgreSQL itself canceled the nested 61-symbol RPC at the 200ms statement deadline (SQLSTATE 57014)"

# Always verify absence of partial row and trigger effects BEFORE the retry.
# The next file drops only the QA sleep trigger and tests commit+replay.
psql -X -v ON_ERROR_STOP=1 \
  -f ops/sql/qa_atomic_core_scan_real_timeout_verify_v01.sql

echo "PASS: genuine statement timeout rollback and safe retry verified in disposable PostgreSQL 17"
