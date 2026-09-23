-- Alpha Hunter private fill readiness for cost validation v0.1
--
-- Purpose:
--   Make the private-fill/account-identity blocker explicit for the sealed
--   profitability experiment without weakening the existing Bitget identity
--   guard or changing scanner credentials.
--
-- No account fingerprint value is exposed by this view.

create or replace view public.alpha_hunter_private_fill_cost_readiness_v01
with (security_invoker=true,security_barrier=true)
as
with specs as (
  select
    s.spec_id,
    s.required_run_source,
    a.started_at_utc
  from public.alpha_hunter_profitability_test_specs_v01 s
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
),
latest_scan as (
  select
    s.spec_id,
    p.run_id,
    p.collected_at_utc,
    p.payload->'private_account' as private_account
  from specs s
  left join lateral (
    select p0.*
    from public.alpha_hunter_snapshots p0
    where p0.payload->'validation_identity'->>'run_source'
      =s.required_run_source
    order by p0.collected_at_utc desc
    limit 1
  ) p on true
),
fill_run as (
  select
    l.spec_id,
    f.source_run_id,
    f.observed_at_utc,
    f.status,
    f.complete,
    f.schema_validated,
    f.fill_count,
    f.pages_fetched,
    f.newest_fill_at_utc,
    f.detail
  from latest_scan l
  left join public.alpha_hunter_fill_traceability_runs f
    on f.source_run_id=l.run_id
)
select
  s.spec_id,
  s.required_run_source,
  l.run_id as latest_source_run_id,
  l.collected_at_utc as latest_source_scan_at_utc,

  coalesce(l.private_account->>'status','NOT_CONFIGURED')
    as private_account_status,
  coalesce(l.private_account->>'account_mode','UNKNOWN')
    as account_mode,
  coalesce(
    (l.private_account->>'account_is_subaccount')::boolean,
    false
  ) as account_is_subaccount,
  coalesce(
    l.private_account->>'account_identity_probe_status',
    'NOT_CONFIGURED'
  ) as account_identity_probe_status,
  coalesce(
    (l.private_account->>'account_identity_match')::boolean,
    false
  ) as account_identity_match,
  coalesce(
    (l.private_account->>'account_identity_expected_configured')::boolean,
    false
  ) as account_identity_expected_configured,

  coalesce(f.status,'MISSING') as fill_traceability_status,
  coalesce(f.complete,false) as fill_traceability_complete,
  coalesce(f.schema_validated,false) as fill_schema_validated,
  coalesce(f.fill_count,0) as fill_count,
  coalesce(f.pages_fetched,0) as fill_pages_fetched,
  f.newest_fill_at_utc,
  f.detail as fill_traceability_detail,

  (
    coalesce(l.private_account->>'status','')='CONNECTED'
    and coalesce(
      (l.private_account->>'account_identity_expected_configured')::boolean,
      false
    )
    and coalesce(
      (l.private_account->>'account_identity_match')::boolean,
      false
    )
  ) as account_identity_gate_met,

  (
    coalesce(f.complete,false)
    and coalesce(f.schema_validated,false)
  ) as fill_traceability_gate_met,

  case
    when coalesce(l.private_account->>'status','')<>'CONNECTED'
      then 'BLOCKED_PRIVATE_ACCOUNT_NOT_CONNECTED'
    when not coalesce(
      (l.private_account->>'account_identity_expected_configured')::boolean,
      false
    )
      then 'BLOCKED_ACCOUNT_IDENTITY_UNPINNED'
    when not coalesce(
      (l.private_account->>'account_identity_match')::boolean,
      false
    )
      then 'BLOCKED_ACCOUNT_IDENTITY_MISMATCH'
    when not coalesce(f.complete,false)
      or not coalesce(f.schema_validated,false)
      then 'BLOCKED_FILL_TRACEABILITY_INCOMPLETE'
    else 'READY_FOR_PROSPECTIVE_FILL_MATCHING'
  end as readiness_status,

  'PIN_EXPECTED_ACCOUNT_IDENTITY_AND_COLLECT_PROSPECTIVE_READ_ONLY_FILLS'::text
    as next_gate,
  true as audit_only,
  true as read_only,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from specs s
left join latest_scan l on l.spec_id=s.spec_id
left join fill_run f on f.spec_id=s.spec_id;

revoke all on public.alpha_hunter_private_fill_cost_readiness_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_private_fill_cost_readiness_v01
  to service_role;
