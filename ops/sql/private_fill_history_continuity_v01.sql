-- Alpha Hunter private fill history continuity audit v0.1
--
-- Read-only diagnostic surface. It compares the current canonical account's
-- fill window with already persisted fill evidence from the same endpoint.
-- It does not assert account identity and does not alter any sealed gate.

create or replace view public.alpha_hunter_private_fill_history_continuity_v01
with (security_invoker=true, security_barrier=true) as
with specs as (
  select
    s.spec_id,
    s.required_run_source
  from public.alpha_hunter_profitability_test_specs_v01 s
),
latest_scan as (
  select
    s.spec_id,
    s.required_run_source,
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
current_fill as (
  select
    l.spec_id,
    l.required_run_source,
    l.run_id as source_run_id,
    l.collected_at_utc as source_scan_at_utc,
    l.private_account,
    f.traceability_run_id,
    f.window_start_utc,
    f.window_end_utc,
    f.endpoint,
    f.status,
    f.complete,
    f.schema_validated,
    f.fill_count,
    f.pages_fetched
  from latest_scan l
  left join lateral (
    select f0.*
    from public.alpha_hunter_fill_traceability_runs f0
    where f0.source_run_id=l.run_id
    order by f0.observed_at_utc desc
    limit 1
  ) f on true
),
history as (
  select
    c.spec_id,
    count(e.*)::bigint as historical_fill_rows_same_window,
    max(e.fill_time_utc) as historical_latest_fill_at_utc,
    count(distinct e.symbol)::integer as historical_symbols_same_window
  from current_fill c
  left join public.alpha_hunter_fill_evidence e
    on e.fill_time_utc>=c.window_start_utc
   and e.fill_time_utc<=c.window_end_utc
   and coalesce(e.evidence->>'endpoint','')=coalesce(c.endpoint,'')
  group by c.spec_id
)
select
  c.spec_id,
  c.required_run_source,
  c.source_run_id as latest_source_run_id,
  c.source_scan_at_utc as latest_source_scan_at_utc,
  c.traceability_run_id,
  c.window_start_utc,
  c.window_end_utc,
  c.endpoint,
  coalesce(c.status,'MISSING') as current_fill_status,
  coalesce(c.complete,false) as current_fill_complete,
  coalesce(c.schema_validated,false) as current_fill_schema_validated,
  coalesce(c.fill_count,0) as current_fill_count,
  coalesce(c.pages_fetched,0) as current_fill_pages_fetched,
  coalesce(
    c.private_account->>'account_identity_probe_status',
    'NOT_CONFIGURED'
  ) as account_identity_probe_status,
  coalesce(
    (c.private_account->>'account_identity_expected_configured')::boolean,
    false
  ) as account_identity_expected_configured,
  coalesce(
    (c.private_account->>'account_identity_match')::boolean,
    false
  ) as account_identity_match,
  coalesce(
    (c.private_account->>'account_is_subaccount')::boolean,
    false
  ) as account_is_subaccount,
  coalesce(h.historical_fill_rows_same_window,0)
    as historical_fill_rows_same_window,
  coalesce(h.historical_symbols_same_window,0)
    as historical_symbols_same_window,
  h.historical_latest_fill_at_utc,
  (
    coalesce(c.fill_count,0)=0
    and coalesce(h.historical_fill_rows_same_window,0)>0
    and coalesce(c.endpoint,'')<>''
  ) as historical_fill_continuity_conflict,
  case
    when c.source_run_id is null
      then 'NO_CANONICAL_SOURCE_RUN'
    when c.traceability_run_id is null
      then 'NO_CURRENT_FILL_TRACEABILITY_RUN'
    when coalesce(c.fill_count,0)>0
      then 'CURRENT_FILLS_PRESENT'
    when coalesce(c.fill_count,0)=0
         and coalesce(h.historical_fill_rows_same_window,0)>0
      then 'HISTORICAL_FILL_CONTINUITY_CONFLICT'
    when coalesce(c.fill_count,0)=0
         and coalesce(h.historical_fill_rows_same_window,0)=0
      then 'NO_HISTORICAL_CONFLICT_OBSERVED'
    else 'INCOMPLETE'
  end as continuity_status,
  case
    when coalesce(c.fill_count,0)=0
         and coalesce(h.historical_fill_rows_same_window,0)>0
      then 'VERIFY_RENDER_BITGET_ACCOUNT_BEFORE_PINNING'
    else 'CONTINUE_READ_ONLY_EVIDENCE_COLLECTION'
  end as next_gate,
  true as audit_only,
  true as read_only,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from current_fill c
left join history h on h.spec_id=c.spec_id;

comment on view public.alpha_hunter_private_fill_history_continuity_v01 is
  'Read-only diagnostic comparing current fill-window observations with historical '
  'fill evidence from the same endpoint. It does not assert account identity.';

revoke all on public.alpha_hunter_private_fill_history_continuity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_private_fill_history_continuity_v01
  to service_role;
