#!/usr/bin/env bash
# Synthetic concurrent duplicate-run test; disposable PostgreSQL ONLY.
set -euo pipefail
: "${PGDATABASE:?}"
[[ "$PGDATABASE" == "isolated_research" ]] || { echo 'REFUSE non-disposable database' >&2; exit 2; }
tmp=$(mktemp -d)
first_pid=''
cleanup() {
  if [[ -n "$first_pid" ]]; then wait "$first_pid" 2>/dev/null || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT

# One synthetic caller per separate PostgreSQL connection. The first caller
# holds the parent unique index key while its second child is delayed.
psql -X -v ON_ERROR_STOP=1 <<'SQL'
create function public.research_concurrent_child_delay() returns trigger
language plpgsql as $$
begin
  if new.run_id='race-same-run' and new.symbol='ETHUSDT' then
    perform pg_sleep(3);
  end if;
  return new;
end $$;
create trigger research_concurrent_child_delay before insert
on public.alpha_hunter_symbol_snapshots
for each row execute function public.research_concurrent_child_delay();

create function public.research_concurrent_call() returns integer
language sql as $$
select public.ah_research_atomic_snapshot_v01(
  jsonb_build_object('run_id','race-same-run',
    'collected_at_utc','2026-11-03T00:00:00Z',
    'version','research-only','product_type','synthetic',
    'symbol_count',2,'error_count',0,
    'payload',jsonb_build_object('run_id','race-same-run')),
  jsonb_build_array(
    jsonb_build_object('run_id','race-same-run','symbol','BTCUSDT',
      'collected_at_utc','2026-11-03T00:00:00Z',
      'state_changed',false,'trade_permission',false,
      'payload',jsonb_build_object('symbol','BTCUSDT')),
    jsonb_build_object('run_id','race-same-run','symbol','ETHUSDT',
      'collected_at_utc','2026-11-03T00:00:00Z',
      'state_changed',false,'trade_permission',false,
      'payload',jsonb_build_object('symbol','ETHUSDT'))
  )
);
$$;
SQL

psql -X -v ON_ERROR_STOP=1 -c 'select public.research_concurrent_call();' >"$tmp/first" 2>&1 &
first_pid=$!
# Synchronise on the actual first parent insert (uncommitted), not a guessed
# delay: the second session must encounter genuine unique-key contention.
ready=0
for i in $(seq 1 80); do
  if psql -X -At -v ON_ERROR_STOP=1 -c "select count(*) from pg_stat_activity where query like '%research_concurrent_call%' and state='active' and pid <> pg_backend_pid();" | grep -q '^[1-9]'; then
    ready=1; break
  fi
  sleep 0.05
done
if [[ "$ready" != 1 ]]; then
  echo 'FAIL: first concurrent writer did not become active' >&2
  cat "$tmp/first" >&2
  exit 1
fi
set +e
psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose >"$tmp/second" 2>&1 <<'SQL'
set lock_timeout = '300ms';
select public.research_concurrent_call();
SQL
second_status=$?
wait "$first_pid"
first_status=$?
first_pid=''
set -e
if [[ "$first_status" != 0 ]] || [[ "$second_status" == 0 ]] ||
   ! grep -Eq '55P03: canceling statement due to lock timeout|23505: duplicate key value violates unique constraint' "$tmp/second"; then
  echo "FAIL: expected first success and second 55P03/23505, got $first_status/$second_status" >&2
  cat "$tmp/first" "$tmp/second" >&2
  exit 1
fi

# Independently read committed data: exactly one parent and two children.
psql -X -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
 if (select count(*) from public.alpha_hunter_snapshots
     where run_id='race-same-run') <> 1
 or (select count(*) from public.alpha_hunter_symbol_snapshots
     where run_id='race-same-run') <> 2 then
  raise exception 'concurrent write violated one-parent/two-child atomicity';
 end if;
end $$;
SQL
echo 'PASS: concurrent same-run contention; first committed, second rejected; exactly one complete snapshot'
