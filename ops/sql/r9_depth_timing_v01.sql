begin;
-- Isolated forward diagnostic; execution never reads these relations.
create table public.alpha_hunter_r9_depth_timing_runs_v01 (
 run_id text not null, phase text not null check(phase in ('START','END')),
 started_at_utc timestamptz not null, recorded_at_utc timestamptz not null default clock_timestamp(),
 status text not null check(status in ('STARTED','COMPLETE','DEGRADED','FAILED')),
 orders_seen integer not null, captures_saved integer not null, capture_failures integer not null,
 error_type text, primary key(run_id,phase)
);
create table public.alpha_hunter_r9_depth_timing_captures_v01 (
 capture_id text primary key, run_id text not null,
 order_id text not null references public.alpha_hunter_paper_orders_v02(order_id),
 requested_at_utc timestamptz not null, received_at_utc timestamptz not null,
 verdict text not null check(verdict in ('NOT_CROSSED','L1_SUFFICIENT',
 'RETURNED_DEPTH_SUFFICIENT_L1_INSUFFICIENT','RETURNED_DEPTH_INSUFFICIENT',
 'CAPTURE_FAILED','RECEIVED_AFTER_EXPIRY')),
 evidence jsonb not null,
 shadow_only boolean not null default true check(shadow_only),
 trade_permission boolean not null default false check(not trade_permission),
 order_path text not null default 'NONE' check(order_path='NONE'),
 check(received_at_utc>=requested_at_utc),
 check(evidence @> '{"fill_proven":false,"profitability_sample_eligible":false}'::jsonb)
);
create index on public.alpha_hunter_r9_depth_timing_captures_v01(order_id,received_at_utc);
alter table public.alpha_hunter_r9_depth_timing_runs_v01 enable row level security;
alter table public.alpha_hunter_r9_depth_timing_captures_v01 enable row level security;
revoke all on public.alpha_hunter_r9_depth_timing_runs_v01,
 public.alpha_hunter_r9_depth_timing_captures_v01 from public,anon,authenticated,service_role;
grant select,insert on public.alpha_hunter_r9_depth_timing_runs_v01,
 public.alpha_hunter_r9_depth_timing_captures_v01 to service_role;
create trigger r9_depth_runs_append_only before update or delete on public.alpha_hunter_r9_depth_timing_runs_v01
 for each row execute function private.alpha_hunter_block_append_only_mutation();
create trigger r9_depth_captures_append_only before update or delete on public.alpha_hunter_r9_depth_timing_captures_v01
 for each row execute function private.alpha_hunter_block_append_only_mutation();
create view public.alpha_hunter_r9_depth_timing_open_v01 with(security_invoker=true) as
 select o.order_id,o.decision_id,o.symbol,o.direction,o.limit_price,o.quantity,o.submitted_at_utc
 from public.alpha_hunter_paper_cohort_members_v09 c
 join public.alpha_hunter_paper_orders_v02 o using(order_id)
 where c.latest_state='SUBMITTED' and o.order_type='LIMIT'
 and o.submitted_at_utc<=clock_timestamp()
 and o.submitted_at_utc>=clock_timestamp()-interval '35 minutes'
 and not exists(select 1 from public.alpha_hunter_paper_fills_v02 f where f.order_id=o.order_id);
create view public.alpha_hunter_r9_depth_timing_gaps_v01 with(security_invoker=true) as
 select order_id,received_at_utc,verdict,
 extract(epoch from received_at_utc-lag(received_at_utc) over(partition by order_id order by received_at_utc))/60 as observation_gap_minutes
 from public.alpha_hunter_r9_depth_timing_captures_v01;
revoke all on public.alpha_hunter_r9_depth_timing_open_v01,
 public.alpha_hunter_r9_depth_timing_gaps_v01 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r9_depth_timing_open_v01,
 public.alpha_hunter_r9_depth_timing_gaps_v01 to service_role;
commit;
