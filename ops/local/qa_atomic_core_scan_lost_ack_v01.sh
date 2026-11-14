#!/usr/bin/env bash
# Harada E3: disposable PG17 only; simulate client losing a successful RPC receipt.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_REF_NAME:-}" != "fix/supabase-write-timeout-qa" || "${PGHOST:-}" != "127.0.0.1" || "${PGDATABASE:-}" != "isolated_atomic_scan_qa" || "${PGUSER:-}" != "postgres" ]]; then
 echo "REFUSED: disposable CI PostgreSQL only" >&2; exit 2
fi
psql -X -v ON_ERROR_STOP=1 -f ops/sql/qa_atomic_core_scan_lost_ack_setup_v01.sql
# First invocation commits; its result is deliberately discarded. No retry before commit.
psql -X -v ON_ERROR_STOP=1 -At -c "SELECT public.alpha_hunter_commit_core_scan_v01(parent_rows,children_rows,signals_rows,features_rows,readiness_rows) FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_LOST_ACK';" >/dev/null
# Independent connection verifies committed state and repeats identical request.
psql -X -v ON_ERROR_STOP=1 -f ops/sql/qa_atomic_core_scan_lost_ack_verify_v01.sql
echo "PASS: E3 synthetic committed-but-lost-ack retry, separate sessions"
