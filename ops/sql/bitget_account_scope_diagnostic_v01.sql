-- Alpha Hunter Bitget account-scope diagnostic v0.1
--
-- Read-only operational diagnostic. This lives under ops/sql and is outside the
-- sealed V14 scientific fingerprint.
--
-- Goal: distinguish a generic zero-fill condition from a probable wrong
-- account/subaccount credential lane using persisted contemporaneous evidence.
-- It does not expose raw Bitget UID or the account fingerprint value.

create or replace view public.alpha_hunter_bitget_account_scope_diagnostic_v01
with (security_invoker=true, security_barrier=true)
as
with current_lane as (
  select
    s.run_id as current_run_id,
    s.collected_at_utc as current_scan_at_utc,
    s.payload->'private_account'->>'status' as current_account_status,
    coalesce(
      (s.payload->'private_account'->>'account_is_subaccount')::boolean,
      false
    ) as current_account_is_subaccount,
    coalesce(
      (s.payload->'private_account'->'accounts'->0->>'account_equity')::numeric,
      0
    ) as current_equity_usdt,
    coalesce(
      (s.payload->'private_account'->>'open_position_count')::integer,
      0
    ) as current_open_position_count
  from public.alpha_hunter_snapshots s
  where s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  order by s.collected_at_utc desc
  limit 1
),
current_fill as (
  select
    c.current_run_id,
    t.status as current_fill_status,
    coalesce(t.fill_count,0) as current_fill_count,
    coalesce(t.complete,false) as current_fill_complete,
    coalesce(t.schema_validated,false) as current_fill_schema_validated
  from current_lane c
  left join lateral (
    select t.*
    from public.alpha_hunter_fill_traceability_runs t
    where t.source_run_id=c.current_run_id
      and t.endpoint='/api/v2/mix/order/fills'
    order by t.observed_at_utc desc
    limit 1
  ) t on true
),
fingerprinted_lane as (
  select
    min(s.collected_at_utc) as first_fingerprinted_lane_seen_at_utc,
    count(*) as fingerprinted_lane_observations
  from public.alpha_hunter_snapshots s
  where s.payload->'private_account' ? 'account_identity_fingerprint'
    and coalesce(
      (s.payload->'private_account'->>'account_is_subaccount')::boolean,
      false
    )=true
),
historical_fill_lane as (
  select
    count(*) as historical_fill_producing_runs_after_first_seen,
    max(t.fill_count) as historical_max_fill_count,
    max(t.observed_at_utc) as historical_latest_fill_run_at_utc,
    max(
      coalesce(
        (s.payload->'private_account'->'accounts'->0->>'account_equity')::numeric,
        0
      )
    ) as historical_max_equity_usdt,
    max(
      coalesce(
        (s.payload->'private_account'->>'open_position_count')::integer,
        0
      )
    ) as historical_max_open_position_count
  from fingerprinted_lane f
  join public.alpha_hunter_fill_traceability_runs t
    on f.first_fingerprinted_lane_seen_at_utc is not null
   and t.observed_at_utc>=f.first_fingerprinted_lane_seen_at_utc
   and t.endpoint='/api/v2/mix/order/fills'
   and t.fill_count>0
   and t.complete=true
   and t.schema_validated=true
  join public.alpha_hunter_snapshots s
    on s.run_id=t.source_run_id
),
diagnostic as (
  select
    clock_timestamp() as checked_at_utc,
    c.current_run_id,
    c.current_scan_at_utc,
    c.current_account_status,
    c.current_account_is_subaccount,
    c.current_equity_usdt,
    c.current_open_position_count,
    cf.current_fill_status,
    coalesce(cf.current_fill_count,0) as current_fill_count,
    coalesce(cf.current_fill_complete,false) as current_fill_complete,
    coalesce(cf.current_fill_schema_validated,false)
      as current_fill_schema_validated,
    f.first_fingerprinted_lane_seen_at_utc,
    f.fingerprinted_lane_observations,
    h.historical_fill_producing_runs_after_first_seen,
    h.historical_max_fill_count,
    h.historical_latest_fill_run_at_utc,
    h.historical_max_equity_usdt,
    h.historical_max_open_position_count,
    (
      c.current_account_status='CONNECTED'
      and c.current_account_is_subaccount=true
      and c.current_equity_usdt=0
      and coalesce(cf.current_fill_count,0)=0
      and coalesce(h.historical_fill_producing_runs_after_first_seen,0)>0
      and coalesce(h.historical_max_equity_usdt,0)>0
    ) as probable_account_scope_mismatch
  from current_lane c
  left join current_fill cf on cf.current_run_id=c.current_run_id
  cross join fingerprinted_lane f
  cross join historical_fill_lane h
)
select
  d.*,
  case
    when d.probable_account_scope_mismatch
      then 'PROBABLE_ACCOUNT_SCOPE_MISMATCH'
    when d.current_account_status<>'CONNECTED'
      then 'CURRENT_ACCOUNT_NOT_CONNECTED'
    when d.current_fill_count=0
      then 'ZERO_FILLS_ACCOUNT_SCOPE_UNRESOLVED'
    else 'NO_ACCOUNT_SCOPE_CONFLICT_DETECTED'
  end as diagnostic_status,
  case
    when d.probable_account_scope_mismatch
      then 'VERIFY_AND_REPLACE_RENDER_BITGET_READ_ONLY_CREDENTIALS_WITH_INTENDED_FILL_PRODUCING_ACCOUNT'
    when d.current_account_status<>'CONNECTED'
      then 'RESTORE_READ_ONLY_BITGET_CONNECTIVITY'
    when d.current_fill_count=0
      then 'VERIFY_ACCOUNT_IDENTITY_BEFORE_PINNING'
    else 'CONTINUE_PROSPECTIVE_FILL_VALIDATION'
  end as next_action,
  true as audit_only,
  true as read_only,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from diagnostic d;

comment on view public.alpha_hunter_bitget_account_scope_diagnostic_v01 is
  'Read-only Bitget credential-lane diagnostic. Uses persisted account/fill '
  'evidence to identify a probable account/subaccount scope mismatch without '
  'exposing raw UID or account fingerprint values.';

revoke all on public.alpha_hunter_bitget_account_scope_diagnostic_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_bitget_account_scope_diagnostic_v01
  to service_role;
