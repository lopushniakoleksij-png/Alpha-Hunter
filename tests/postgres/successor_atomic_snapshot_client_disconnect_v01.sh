#!/usr/bin/env bash
# Disposable PG16/17 only: client loss AFTER confirmed COMMIT, then safe readback/retry.
set -euo pipefail
: "${PGDATABASE:?}"
[[ "$PGDATABASE" == "isolated_research" ]] || { echo 'REFUSE non-disposable database' >&2; exit 2; }
tmp=$(mktemp -d)
client_pid=''
cleanup() {
  if [[ -n "$client_pid" ]]; then kill "$client_pid" 2>/dev/null || true; wait "$client_pid" 2>/dev/null || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT

# The client receives a successful COMMIT then becomes unreachable while
# waiting for an unrelated response. The caller must rely on independent
# committed-state readback rather than blindly replaying an uncertain write.
psql -X -v ON_ERROR_STOP=1 >"$tmp/client" 2>&1 <<'SQL' &
begin;
select public.ah_research_atomic_snapshot_v01(
 jsonb_build_object('run_id','disconnect-after-commit','collected_at_utc','2026-11-03T00:00:00Z',
  'version','research-only','product_type','synthetic','symbol_count',2,'error_count',0,
  'payload',jsonb_build_object('run_id','disconnect-after-commit')),
 jsonb_build_array(
  jsonb_build_object('run_id','disconnect-after-commit','symbol','BTCUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','BTCUSDT')),
  jsonb_build_object('run_id','disconnect-after-commit','symbol','ETHUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','ETHUSDT'))
 ));
commit;
select pg_sleep(30);
SQL
client_pid=$!

# Poll an independent session until the exact synthetic run is durably
# visible AND the original client is still alive. No timing-only assertion.
observed=0
for i in $(seq 1 100); do
  counts=$(psql -X -At -v ON_ERROR_STOP=1 -c "select (select count(*) from public.alpha_hunter_snapshots where run_id='disconnect-after-commit')::text || ':' || (select count(*) from public.alpha_hunter_symbol_snapshots where run_id='disconnect-after-commit')::text")
  if [[ "$counts" == '1:2' ]] && kill -0 "$client_pid" 2>/dev/null; then
    observed=1; break
  fi
  sleep 0.05
done
if [[ "$observed" != 1 ]]; then
  echo 'FAIL: committed snapshot was not independently visible with client alive' >&2
  cat "$tmp/client" >&2
  exit 1
fi

# Disconnect only this synthetic psql client; never terminate the server.
kill -TERM "$client_pid"
wait "$client_pid" 2>/dev/null || true
client_pid=''

# Readback is the recovery oracle; a duplicate retry must fail closed and
# leave the original complete parent/children untouched.
set +e
psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose >"$tmp/retry" 2>&1 <<'SQL'
select public.ah_research_atomic_snapshot_v01(
 jsonb_build_object('run_id','disconnect-after-commit','collected_at_utc','2026-11-03T00:00:00Z',
  'version','research-only','product_type','synthetic','symbol_count',2,'error_count',0,
  'payload',jsonb_build_object('run_id','disconnect-after-commit')),
 jsonb_build_array(
  jsonb_build_object('run_id','disconnect-after-commit','symbol','BTCUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','BTCUSDT')),
  jsonb_build_object('run_id','disconnect-after-commit','symbol','ETHUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','ETHUSDT'))
 ));
SQL
retry_status=$?
set -e
if [[ "$retry_status" == 0 ]] || ! grep -q '23505:' "$tmp/retry"; then
  echo 'FAIL: duplicate retry did not fail closed with 23505' >&2
  cat "$tmp/retry" >&2
  exit 1
fi
psql -X -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
 if (select count(*) from public.alpha_hunter_snapshots where run_id='disconnect-after-commit') <> 1
 or (select count(*) from public.alpha_hunter_symbol_snapshots where run_id='disconnect-after-commit') <> 2
 or (select count(distinct symbol) from public.alpha_hunter_symbol_snapshots where run_id='disconnect-after-commit') <> 2 then
   raise exception 'disconnect recovery mutated or lost committed evidence';
 end if;
end $$;
SQL
echo 'PASS: client disconnected after COMMIT; independent readback 1:2; duplicate retry 23505; original unchanged'
