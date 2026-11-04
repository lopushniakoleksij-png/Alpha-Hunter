#!/usr/bin/env bash
# Disposable PG16/17 only. Disconnect DURING COMMIT via deferred trigger.
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

# A deferred constraint trigger executes only at COMMIT. This is a synthetic
# timing barrier, not a simulation of network delivery/acknowledgement.
psql -X -v ON_ERROR_STOP=1 <<'SQL'
create function public.research_commit_barrier() returns trigger
language plpgsql as $$
begin
 if new.run_id='disconnect-during-commit' then
   perform pg_sleep(4);
 end if;
 return new;
end $$;
create constraint trigger research_commit_barrier
after insert on public.alpha_hunter_snapshots
deferrable initially deferred for each row
execute function public.research_commit_barrier();
SQL

PGAPPNAME='research-inflight-commit' psql -X -v ON_ERROR_STOP=1 >"$tmp/client" 2>&1 <<'SQL' &
begin;
select public.ah_research_atomic_snapshot_v01(
 jsonb_build_object('run_id','disconnect-during-commit','collected_at_utc','2026-11-03T00:00:00Z',
 'version','research-only','product_type','synthetic','symbol_count',2,'error_count',0,
 'payload',jsonb_build_object('run_id','disconnect-during-commit')),
 jsonb_build_array(
 jsonb_build_object('run_id','disconnect-during-commit','symbol','BTCUSDT',
 'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
 'payload',jsonb_build_object('symbol','BTCUSDT')),
 jsonb_build_object('run_id','disconnect-during-commit','symbol','ETHUSDT',
 'collected_at_utc','2026-11-03T00:00:00Z','state_changed',false,'trade_permission',false,
 'payload',jsonb_build_object('symbol','ETHUSDT'))
 ));
commit;
SQL
client_pid=$!

# Synchronise with the actual deferred trigger running during COMMIT.
seen=0
for i in $(seq 1 100); do
 state=$(psql -X -At -v ON_ERROR_STOP=1 -c "select count(*) from pg_stat_activity where application_name='research-inflight-commit' and query='commit;' and state='active' and wait_event='PgSleep';")
 if [[ "$state" == 1 ]]; then seen=1; break; fi
 kill -0 "$client_pid" 2>/dev/null || break
 sleep 0.05
done
if [[ "$seen" != 1 ]]; then
 echo 'FAIL: did not observe in-flight deferred COMMIT barrier' >&2
 cat "$tmp/client" >&2
 exit 1
fi

# Kill only the synthetic client; allow the server to resolve its transaction.
kill -KILL "$client_pid" 2>/dev/null || true
wait "$client_pid" 2>/dev/null || true
client_pid=''
settled=0
for i in $(seq 1 150); do
 n=$(psql -X -At -v ON_ERROR_STOP=1 -c "select count(*) from pg_stat_activity where application_name='research-inflight-commit';")
 if [[ "$n" == 0 ]]; then settled=1; break; fi
 sleep 0.05
done
[[ "$settled" == 1 ]] || { echo 'FAIL: orphaned synthetic backend did not settle' >&2; exit 1; }

# An unknown client outcome must never be treated as a confirmed success.
# Independently observe either fully rolled back (0:0) or fully committed (1:2).
counts=$(psql -X -At -v ON_ERROR_STOP=1 -c "select (select count(*) from public.alpha_hunter_snapshots where run_id='disconnect-during-commit')::text || ':' || (select count(*) from public.alpha_hunter_symbol_snapshots where run_id='disconnect-during-commit')::text")
case "$counts" in
 '0:0'|'1:2') ;;
 *) echo "FAIL: partial or duplicate snapshot after in-flight disconnect: $counts" >&2; exit 1 ;;
esac
echo "PASS: disconnect during deferred COMMIT; independent settled readback $counts; no partial snapshot"
