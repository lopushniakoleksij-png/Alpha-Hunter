-- Alpha Hunter Bitget account-scope diagnostic v0.2
--
-- Read-only operational diagnostic. Lives under ops/sql and is outside the
-- sealed V14 scientific fingerprint.
--
-- v0.2 fixes an evidence-classification defect in v0.1:
-- historical fill-producing snapshots predate the account fingerprint and
-- subaccount fields. Missing historical identity fields must never be coerced
-- into evidence that the historical lane was a different account or a main
-- account.
--
-- This view separates:
-- 1) continuity conflict (current zero-fill/zero-equity vs historical fills),
-- 2) directly comparable fingerprint evidence, and
-- 3) unresolved historical identity because old snapshots lack fingerprints.
--
-- It never exposes raw Bitget UID/parentId or secrets.

create or replace view public.alpha_hunter_bitget_account_scope_diagnostic_v02
with (security_invoker=true, security_barrier=true)
as
with current_lane as (
  select
    s.run_id as current_run_id,
    s.collected_at_utc as current_scan_at_utc,
    s.payload->'private_account'->>'status' as current_account_status,
    nullif(
      s.payload->'private_account'->>'account_identity_fingerprint',
      ''
    ) as current_account_identity_fingerprint,
    case
      when s.payload->'private_account' ? 'account_is_subaccount'
        then (s.payload->'private_account'->>'account_is_subaccount')::boolean
      else null
    end as current_account_is_subaccount,
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
historical_fill_lane as (
  select
    count(*) as historical_fill_producing_runs,
    max(t.fill_count) as historical_max_fill_count,
    min(t.observed_at_utc) as historical_first_fill_run_at_utc,
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
    ) as historical_max_open_position_count,
    count(*) filter (
      where s.payload->'private_account' ? 'account_identity_fingerprint'
        and nullif(
          s.payload->'private_account'->>'account_identity_fingerprint',
          ''
        ) is not null
    ) as historical_fingerprint_observations,
    count(*) filter (
      where s.payload->'private_account' ? 'account_is_subaccount'
    ) as historical_subaccount_observations,
    count(*) filter (
      where s.payload->'private_account' ? 'account_is_subaccount'
        and (s.payload->'private_account'->>'account_is_subaccount')::boolean=true
    ) as historical_subaccount_true_runs,
    count(*) filter (
      where s.payload->'private_account' ? 'account_is_subaccount'
        and (s.payload->'private_account'->>'account_is_subaccount')::boolean=false
    ) as historical_subaccount_false_runs
  from public.alpha_hunter_fill_traceability_runs t
  join public.alpha_hunter_snapshots s
    on s.run_id=t.source_run_id
  where t.endpoint='/api/v2/mix/order/fills'
    and t.fill_count>0
    and t.complete=true
    and t.schema_validated=true
),
fingerprint_comparison as (
  select
    count(*) filter (
      where c.current_account_identity_fingerprint is not null
        and s.payload->'private_account' ? 'account_identity_fingerprint'
        and nullif(
          s.payload->'private_account'->>'account_identity_fingerprint',
          ''
        )=c.current_account_identity_fingerprint
    ) as historical_same_fingerprint_fill_runs,
    count(*) filter (
      where c.current_account_identity_fingerprint is not null
        and s.payload->'private_account' ? 'account_identity_fingerprint'
        and nullif(
          s.payload->'private_account'->>'account_identity_fingerprint',
          ''
        ) is not null
        and nullif(
          s.payload->'private_account'->>'account_identity_fingerprint',
          ''
        )<>c.current_account_identity_fingerprint
    ) as historical_different_fingerprint_fill_runs
  from current_lane c
  cross join public.alpha_hunter_fill_traceability_runs t
  join public.alpha_hunter_snapshots s
    on s.run_id=t.source_run_id
  where t.endpoint='/api/v2/mix/order/fills'
    and t.fill_count>0
    and t.complete=true
    and t.schema_validated=true
),
diagnostic as (
  select
    clock_timestamp() as checked_at_utc,
    c.current_run_id,
    c.current_scan_at_utc,
    c.current_account_status,
    c.current_account_identity_fingerprint is not null
      as current_fingerprint_present,
    c.current_account_is_subaccount,
    c.current_equity_usdt,
    c.current_open_position_count,
    cf.current_fill_status,
    coalesce(cf.current_fill_count,0) as current_fill_count,
    coalesce(cf.current_fill_complete,false) as current_fill_complete,
    coalesce(cf.current_fill_schema_validated,false)
      as current_fill_schema_validated,
    h.historical_fill_producing_runs,
    h.historical_max_fill_count,
    h.historical_first_fill_run_at_utc,
    h.historical_latest_fill_run_at_utc,
    h.historical_max_equity_usdt,
    h.historical_max_open_position_count,
    h.historical_fingerprint_observations,
    h.historical_subaccount_observations,
    h.historical_subaccount_true_runs,
    h.historical_subaccount_false_runs,
    f.historical_same_fingerprint_fill_runs,
    f.historical_different_fingerprint_fill_runs,
    (
      c.current_account_status='CONNECTED'
      and c.current_equity_usdt=0
      and coalesce(cf.current_fill_count,0)=0
      and coalesce(h.historical_fill_producing_runs,0)>0
      and coalesce(h.historical_max_equity_usdt,0)>0
    ) as historical_account_continuity_conflict,
    (
      c.current_account_identity_fingerprint is not null
      and coalesce(f.historical_different_fingerprint_fill_runs,0)>0
      and coalesce(f.historical_same_fingerprint_fill_runs,0)=0
    ) as proven_fingerprint_mismatch,
    (
      coalesce(h.historical_fill_producing_runs,0)>0
      and coalesce(h.historical_fingerprint_observations,0)=0
    ) as historical_identity_not_comparable
  from current_lane c
  left join current_fill cf on cf.current_run_id=c.current_run_id
  cross join historical_fill_lane h
  cross join fingerprint_comparison f
)
select
  d.*,
  case
    when d.current_account_status<>'CONNECTED'
      then 'CURRENT_ACCOUNT_NOT_CONNECTED'
    when d.proven_fingerprint_mismatch
      then 'PROVEN_FINGERPRINT_MISMATCH'
    when d.historical_account_continuity_conflict
         and d.historical_identity_not_comparable
      then 'CONTINUITY_CONFLICT_HISTORICAL_IDENTITY_NOT_COMPARABLE'
    when d.historical_account_continuity_conflict
      then 'ACCOUNT_SCOPE_CONFLICT_REQUIRES_IDENTITY_VERIFICATION'
    when d.current_fill_count=0
      then 'ZERO_FILLS_ACCOUNT_SCOPE_UNRESOLVED'
    else 'NO_ACCOUNT_SCOPE_CONFLICT_DETECTED'
  end as diagnostic_status,
  case
    when d.current_account_status<>'CONNECTED'
      then 'RESTORE_READ_ONLY_BITGET_CONNECTIVITY'
    when d.proven_fingerprint_mismatch
      then 'VERIFY_INTENDED_ACCOUNT_THEN_REPLACE_READ_ONLY_CREDENTIALS'
    when d.historical_account_continuity_conflict
         and d.historical_identity_not_comparable
      then 'INDEPENDENTLY_VERIFY_INTENDED_BITGET_ACCOUNT_OR_SUBACCOUNT_BEFORE_ANY_PINNING_OR_CREDENTIAL_CHANGE'
    when d.historical_account_continuity_conflict
      then 'VERIFY_ACCOUNT_IDENTITY_AND_SCOPE_BEFORE_PINNING'
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

comment on view public.alpha_hunter_bitget_account_scope_diagnostic_v02 is
  'Read-only Bitget account-scope diagnostic. Separates continuity conflict '
  'from proven fingerprint mismatch and treats missing historical identity '
  'fields as not comparable rather than as mismatch evidence.';

revoke all on public.alpha_hunter_bitget_account_scope_diagnostic_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_bitget_account_scope_diagnostic_v02
  to service_role;
