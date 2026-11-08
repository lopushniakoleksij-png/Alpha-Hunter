#!/usr/bin/env bash
# ALPHA HUNTER P0 / HARADA B5-B8: compare restored PRIVATE clone
# structural hashes, critical private functions and extension versions.
# This is READ-ONLY, prints NO function SQL, row payloads or credentials.
# This script CANNOT restore a dump, prove dynamic SQL equivalence, or issue
# independent DBA approval. Run ONLY inside existing authenticated Codespace.
set -Eeuo pipefail
set +x
umask 077

if [[ "$(printenv CODESPACES || true)" != "true" ]] ||
   [[ "$(git branch --show-current 2>/dev/null || true)" != "fix/supabase-write-timeout-qa" ]] ||
   [[ "$(printenv GITHUB_ACTIONS || true)" == "true" ]]; then
  echo "REFUSED: existing Codespace isolated draft branch only; not GitHub Actions."
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: local Docker unavailable."
  exit 3
fi
container="alpha-hunter-private-postgres17-qa"
dbname="alpha_hunter_private_qa"
state="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)"
network="$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$container" 2>/dev/null || true)"
if [[ "$state" != "true" || "$network" != "none" ]]; then
  echo "BLOCKED: named OFFLINE private QA container missing or network not isolated."
  echo "REQUIRED_CONTAINER=alpha-hunter-private-postgres17-qa"
  echo "REQUIRED_NETWORK_MODE=none"
  exit 3
fi

# Direct local Unix socket only; cannot use PGHOST/PGPORT to connect remotely.
qa_psql() {
  docker exec -i -u postgres \
    -e 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=30000' \
    "$container" psql -X -q -A -t -F '|' -v ON_ERROR_STOP=1 \
    -h /var/run/postgresql -d "$dbname"
}
id="$(printf "SELECT current_database()||'|'||current_user||'|'||current_setting('server_version_num');\n" | qa_psql)"
case "$id" in
 alpha_hunter_private_qa\|postgres\|1700*) ;;
 *) echo "REFUSED: QA database/role/version identity invalid."; exit 2 ;;
esac

base="$HOME/.alpha-hunter-private-dbqa"
if [[ ! -d "$base" || -L "$base" ]]; then
  echo "BLOCKED: private baseline results directory unavailable."
  exit 3
fi
fprint="$(mktemp "$base/.clone-fingerprint.XXXXXXXX")"
funcs="$(mktemp "$base/.clone-critical-functions.XXXXXXXX")"
trap 'rm -f "$fprint" "$funcs"' EXIT

qa_psql < ops/sql/readonly_stage2_structural_fingerprint_v01.sql > "$fprint"
if [[ ! -s "$fprint" ]]; then
  echo "BLOCKED: no clone fingerprint results."
  exit 3
fi
IFS='|' read -r tables rls cols indexes policies triggers bearing funcs_count definers \
  col_hash index_hash trigger_hash grant_hash < "$fprint"

expected_counts="128|128|3012|360|0|131|108|36|21"
actual_counts="$tables|$rls|$cols|$indexes|$policies|$triggers|$bearing|$funcs_count|$definers"
failed=0
if [[ "$actual_counts" != "$expected_counts" ]]; then
  echo "FAIL: clone public-table/RLS/index/trigger counts differ from production baseline."
  failed=1
fi
if [[ "$col_hash" != "c802a3e3d96d620a20adc8c3af350472" ]]; then
 echo "FAIL: column fingerprint mismatch."; failed=1
fi
if [[ "$index_hash" != "5a7e8cbe8b8450677f6be84a77caaa6e" ]]; then
 echo "FAIL: index fingerprint mismatch."; failed=1
fi
if [[ "$trigger_hash" != "5c5b202307ef6bb57b4a9b08082c2a1e" ]]; then
 echo "FAIL: trigger/function fingerprint mismatch."; failed=1
fi
if [[ "$grant_hash" != "c9785c793fa51a732c2edc96ba22c7eb" ]]; then
 echo "FAIL: grants/RLS fingerprint mismatch."; failed=1
fi

qa_psql <<'SQL' > "$funcs"
SELECT n.nspname||'.'||p.proname, md5(pg_get_functiondef(p.oid))
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='private'
AND p.proname IN (
 'alpha_hunter_capture_strategy_observations_v01',
 'alpha_hunter_capture_shadow_decision_quote_v01',
 'alpha_hunter_auto_freeze_execution_decision_v02',
 'alpha_hunter_capture_payoff_geometry_health_v01',
 'alpha_hunter_create_calibrated_paper_order_v02',
 'alpha_hunter_enqueue_strategy_24h_outcome_v01'
)
ORDER BY p.proname;
SQL
while IFS='|' read -r name expected; do
  found="$(awk -F'|' -v n="$name" '$1==n {print $2}' "$funcs")"
  if [[ "$found" != "$expected" ]]; then
    echo "FAIL: critical private function digest mismatch: $name"
    failed=1
  fi
done <<'EXPECTED'
private.alpha_hunter_auto_freeze_execution_decision_v02|2caefa517ee67735917497ccdba350fe
private.alpha_hunter_capture_payoff_geometry_health_v01|cea4e21b84587377fd665e21d2763d6c
private.alpha_hunter_capture_shadow_decision_quote_v01|88af26209fa503cbdf4ad9cf29eb09b5
private.alpha_hunter_capture_strategy_observations_v01|52b3b76ecb79ed9694c5a3063a8c81ab
private.alpha_hunter_create_calibrated_paper_order_v02|c05fc276562bba077d3ca48a88b3a3a1
private.alpha_hunter_enqueue_strategy_24h_outcome_v01|18ed88128252c57891fa66a680cb1028
EXPECTED

while IFS='|' read -r ext version schema; do
  if ! grep -Fxq "$ext|$version|$schema" "$fprint"; then
    echo "FAIL: extension version or schema differs: $ext"
    failed=1
  fi
done <<'EXTENSIONS'
http|1.6|extensions
pg_cron|1.6.4|pg_catalog
pg_net|0.20.4|extensions
pg_stat_statements|1.11|extensions
pgcrypto|1.3|extensions
plpgsql|1.0|pg_catalog
supabase_vault|0.3.1|vault
uuid-ossp|1.1|extensions
EXTENSIONS

if (( failed != 0 )); then
  echo "FAIL: clone does NOT match current verified structural baseline."
  echo "No migrations, production writes or benchmarks attempted."
  exit 3
fi

echo "PASS: private QA clone structural metadata, 6 critical functions and 8 extension identities match inspected baseline."
echo "NOT CERTIFIED: dynamic SQL dependencies, role ownership, runtime GUCs, trigger side effects, scientific results and performance."
echo "NEXT_GATE: inspect private dependency graph + run actual 30/50/61 atomic RPC benchmarks using synthetic data."
