#!/usr/bin/env bash
# Disposable PostgreSQL only. Never point this script at production.
set -euo pipefail
: "${PGDATABASE:?A disposable PGDATABASE is required}"
if [[ "${PGDATABASE}" != "isolated_research" ]]; then
  echo "REFUSING non-disposable database" >&2
  exit 2
fi

# The previous integration fixture has created disposable tables and function.
# The first child may be inserted; the second is delayed until the server
# cancels the *whole* SELECT statement with SQLSTATE 57014.
psql -X -v ON_ERROR_STOP=1 <<'SQL'
create function public.research_delay_timeout_child() returns trigger
language plpgsql as $$
begin
  if new.run_id = 'timeout-57014' and new.symbol = 'ETHUSDT' then
    perform pg_sleep(2);
  end if;
  return new;
end $$;
create trigger research_delay_timeout_child before insert
on public.alpha_hunter_symbol_snapshots
for each row execute function public.research_delay_timeout_child();
SQL

set +e
result=$(psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose <<'SQL' 2>&1
set statement_timeout = '250ms';
select public.ah_research_atomic_snapshot_v01(
  jsonb_build_object(
    'run_id','timeout-57014','collected_at_utc','2026-11-03T00:00:00Z',
    'version','research-only','product_type','synthetic','symbol_count',2,
    'error_count',0,'payload',jsonb_build_object('run_id','timeout-57014')),
  jsonb_build_array(
    jsonb_build_object('run_id','timeout-57014','symbol','BTCUSDT',
      'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,
      'trade_permission',false,'payload',jsonb_build_object('symbol','BTCUSDT')),
    jsonb_build_object('run_id','timeout-57014','symbol','ETHUSDT',
      'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,
      'trade_permission',false,'payload',jsonb_build_object('symbol','ETHUSDT'))
  )
);
SQL
)
status=$?
set -e
if [[ "$status" -eq 0 ]] || ! grep -q '57014: canceling statement due to statement timeout' <<< "$result"; then
  echo "FAIL: expected real SQLSTATE 57014, got exit=$status" >&2
  echo "$result" >&2
  exit 1
fi

# The cancelled statement must not persist either parent or first child.
# The psql connection is new, so its timeout setting cannot mask the check.
psql -X -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
  if exists(select 1 from public.alpha_hunter_snapshots
            where run_id='timeout-57014')
     or exists(select 1 from public.alpha_hunter_symbol_snapshots
               where run_id='timeout-57014') then
    raise exception '57014 cancellation left partially persisted canonical data';
  end if;
end $$;
SQL
echo 'PASS: genuine SQLSTATE 57014, zero parent and child rows after cancellation'
