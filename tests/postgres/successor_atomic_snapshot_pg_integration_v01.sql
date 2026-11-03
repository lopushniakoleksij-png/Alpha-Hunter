-- Disposable PostgreSQL integration proof only; NO production credentials.
\set ON_ERROR_STOP on
create table public.alpha_hunter_snapshots (
 run_id text primary key, collected_at_utc timestamptz not null,
 version text not null, product_type text not null, symbol_count integer not null,
 error_count integer not null default 0, payload jsonb not null
);
create table public.alpha_hunter_symbol_snapshots (
 run_id text not null references public.alpha_hunter_snapshots(run_id),
 symbol text not null, collected_at_utc timestamptz not null,
 state text, previous_state text, state_changed boolean not null default false,
 trade_permission boolean not null default false, direction text,
 reward_risk double precision, last_price double precision,
 open_interest double precision, funding_rate double precision,
 data_integrity_score integer, error text, payload jsonb not null,
 primary key(run_id,symbol)
);
\ir ../../research/successor_atomic_snapshot_v01.sql

-- Fixture generates a valid 2-symbol compact snapshot without production data.
create function pg_temp.parent_for(p_run text) returns jsonb language sql as $$
 select jsonb_build_object(
 'run_id',p_run,'collected_at_utc','2026-11-03T00:00:00Z',
 'version','research-only','product_type','synthetic',
 'symbol_count',2,'error_count',0,
 'payload',jsonb_build_object('run_id',p_run,'symbols',jsonb_build_array(
 jsonb_build_object('symbol','BTCUSDT'),jsonb_build_object('symbol','ETHUSDT'))))
$$;
create function pg_temp.children_for(p_run text) returns jsonb language sql as $$
 select jsonb_build_array(
 jsonb_build_object('run_id',p_run,'symbol','BTCUSDT','collected_at_utc','2026-11-03T00:00:00Z',
 'state_changed',false,'trade_permission',false,'payload',jsonb_build_object('symbol','BTCUSDT')),
 jsonb_build_object('run_id',p_run,'symbol','ETHUSDT','collected_at_utc','2026-11-03T00:00:00Z',
 'state_changed',false,'trade_permission',false,'payload',jsonb_build_object('symbol','ETHUSDT')))
$$;

-- Real PG execution: complete insert and exact count.
do $$
declare n integer;
begin
 n := public.ah_research_atomic_snapshot_v01(
 pg_temp.parent_for('complete'),pg_temp.children_for('complete'));
 if n <> 2 or (select count(*) from public.alpha_hunter_symbol_snapshots where run_id='complete') <> 2 then
 raise exception 'complete insert incorrect';
 end if;
end $$;

-- The function's validation must reject foreign, duplicate and partial children.
do $$
declare p text; c jsonb; rejected boolean;
begin
 foreach p in array array['foreign','duplicate','partial','payload-mismatch','parent-mismatch'] loop
  c := pg_temp.children_for(p);
  if p='foreign' then
   c := jsonb_set(c,'{1,run_id}','"wrong"');
  elsif p='duplicate' then
   c := jsonb_set(c,'{1,symbol}','"BTCUSDT"');
  elsif p='partial' then
   c := c - 1;
  elsif p='payload-mismatch' then
   c := jsonb_set(c,'{1,payload,symbol}','"WRONG"');
  end if;
  rejected := false;
  begin
   perform public.ah_research_atomic_snapshot_v01(
    case when p='parent-mismatch' then jsonb_set(pg_temp.parent_for(p),'{payload,run_id}','"wrong"')
    else pg_temp.parent_for(p) end,c);
  exception when others then rejected := true;
  end;
  if not rejected then raise exception 'invalid % accepted',p; end if;
  if exists(select 1 from public.alpha_hunter_snapshots where run_id=p)
     or exists(select 1 from public.alpha_hunter_symbol_snapshots where run_id=p)
  then raise exception 'partial persistence after invalid %',p; end if;
 end loop;
end $$;

-- Force failure on SECOND child after parent and first child have been written.
create function public.research_reject_second_child() returns trigger language plpgsql as $$
begin
 if new.run_id='forced-error' and new.symbol='ETHUSDT' then
  raise exception 'synthetic child write failure';
 end if;
 return new;
end $$;
create trigger research_reject_second before insert on public.alpha_hunter_symbol_snapshots
 for each row execute function public.research_reject_second_child();
do $$
declare rejected boolean := false;
begin
 begin
  perform public.ah_research_atomic_snapshot_v01(
   pg_temp.parent_for('forced-error'),pg_temp.children_for('forced-error'));
 exception when others then rejected := true;
 end;
 if not rejected then raise exception 'forced child failure was not observed'; end if;
 if exists(select 1 from public.alpha_hunter_snapshots where run_id='forced-error')
 or exists(select 1 from public.alpha_hunter_symbol_snapshots where run_id='forced-error')
 then raise exception 'atomic rollback failed after child insert error'; end if;
end $$;

-- A duplicate parent must not overwrite immutable canonical evidence.
do $$
declare rejected boolean := false;
begin
 begin
  perform public.ah_research_atomic_snapshot_v01(
   pg_temp.parent_for('complete'),pg_temp.children_for('complete'));
 exception when unique_violation then rejected := true;
 end;
 if not rejected then raise exception 'duplicate parent was not rejected'; end if;
 if (select count(*) from public.alpha_hunter_symbol_snapshots where run_id='complete') <> 2
 then raise exception 'existing evidence mutated'; end if;
end $$;
\echo 'PASS: PG atomic success, invalid inputs, forced child rollback, immutable duplicate'
