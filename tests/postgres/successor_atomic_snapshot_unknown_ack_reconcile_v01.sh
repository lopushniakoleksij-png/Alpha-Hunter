#!/usr/bin/env bash
# Readback classification after an unknown COMMIT acknowledgement, disposable PG only.
set -euo pipefail
: "${PGDATABASE:?}"
[[ "$PGDATABASE" == "isolated_research" ]] || { echo 'REFUSE non-disposable database' >&2; exit 2; }
psql -X -v ON_ERROR_STOP=1 <<'SQL'
-- This is a research-only oracle: no retry is authorised by an ambiguous ACK
-- unless an independent, exact-run readback establishes ABSENT.
create function pg_temp.reconcile_unknown_commit(p_run text) returns text
language plpgsql as $$
declare
  parents integer;
  children integer;
  valid_children integer;
  valid_parent integer;
begin
  select count(*), count(*) filter (where payload->>'run_id'=p_run
    and symbol_count=2 and error_count=0)
  into parents,valid_parent from public.alpha_hunter_snapshots where run_id=p_run;
  select count(*), count(*) filter (where
    symbol in ('BTCUSDT','ETHUSDT')
    and payload->>'symbol'=symbol
    and trade_permission=false and state_changed=false)
  into children,valid_children from public.alpha_hunter_symbol_snapshots where run_id=p_run;
  if parents=0 and children=0 then return 'ABSENT'; end if;
  if parents=1 and valid_parent=1 and children=2 and valid_children=2
     and (select count(distinct symbol) from public.alpha_hunter_symbol_snapshots where run_id=p_run)=2
  then return 'COMPLETE'; end if;
  return 'INCOMPLETE';
end $$;
do $$
begin
  if pg_temp.reconcile_unknown_commit('unknown-ack-reconcile') <> 'ABSENT' then
    raise exception 'unwritten run must classify ABSENT';
  end if;
end $$;
-- An ABSENT run may be published exactly once using the same atomic contract.
select public.ah_research_atomic_snapshot_v01(
 jsonb_build_object('run_id','unknown-ack-reconcile','collected_at_utc','2026-11-03T00:00:00Z',
  'version','research-only','product_type','synthetic','symbol_count',2,'error_count',0,
  'payload',jsonb_build_object('run_id','unknown-ack-reconcile')),
 jsonb_build_array(
  jsonb_build_object('run_id','unknown-ack-reconcile','symbol','BTCUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','BTCUSDT')),
  jsonb_build_object('run_id','unknown-ack-reconcile','symbol','ETHUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','ETHUSDT'))
 ));
do $$
begin
 if pg_temp.reconcile_unknown_commit('unknown-ack-reconcile') <> 'COMPLETE' then
   raise exception 'committed complete run must classify COMPLETE';
 end if;
end $$;
-- Simulate an inconsistent readback *only inside a rolled-back transaction*.
-- An incomplete result must never be interpreted as ABSENT or COMPLETE.
begin;
update public.alpha_hunter_symbol_snapshots
 set payload=jsonb_build_object('symbol','WRONG')
 where run_id='unknown-ack-reconcile' and symbol='ETHUSDT';
do $$
begin
 if pg_temp.reconcile_unknown_commit('unknown-ack-reconcile') <> 'INCOMPLETE' then
   raise exception 'corrupt child must fail closed as INCOMPLETE';
 end if;
end $$;
rollback;
do $$
begin
 if pg_temp.reconcile_unknown_commit('unknown-ack-reconcile') <> 'COMPLETE' then
   raise exception 'rollback must preserve original complete evidence';
 end if;
end $$;
SQL
# Replaying a COMPLETE run must fail on its immutable parent identity.
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
if psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose >"$tmp" 2>&1 <<'SQL'
select public.ah_research_atomic_snapshot_v01(
 jsonb_build_object('run_id','unknown-ack-reconcile','collected_at_utc','2026-11-03T00:00:00Z',
  'version','research-only','product_type','synthetic','symbol_count',2,'error_count',0,
  'payload',jsonb_build_object('run_id','unknown-ack-reconcile')),
 jsonb_build_array(
  jsonb_build_object('run_id','unknown-ack-reconcile','symbol','BTCUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','BTCUSDT')),
  jsonb_build_object('run_id','unknown-ack-reconcile','symbol','ETHUSDT',
   'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('symbol','ETHUSDT'))
 ));
SQL
then echo 'FAIL: duplicate unknown-ack retry was accepted' >&2; exit 1
fi
grep -q '23505:' "$tmp" || { echo 'FAIL: retry was not rejected with SQLSTATE 23505' >&2; cat "$tmp" >&2; exit 1; }
echo 'PASS: unknown-ack readback ABSENT/COMPLETE/INCOMPLETE; rollback preserves original; duplicate retry 23505'
