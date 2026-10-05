begin;

-- R10 horizon + profitability binding v0.1.
--
-- Inactive scientific plumbing only. This migration inserts no spec,
-- preregistration, runtime verification, activation, admission, order, fill,
-- or outcome rows. Live/exchange authority remains disabled.
--
-- The runtime keeps reading the historical v09 protection view name for
-- compatibility, but cohort identity below is now explicit and disjoint:
--   legacy -> no horizon timeout
--   R9     -> frozen R9 admission window + optional halted-R9 management bridge
--   R10    -> immutable order admission identity + exact R10 activation

create or replace view public.alpha_hunter_paper_protection_horizon_open_v09
with (security_invoker=true,security_barrier=true)
as
with r9 as (
  select
    a.*,
    least(
      a.admission_cutoff_at_utc,
      coalesce(h.halted_at_utc,a.admission_cutoff_at_utc)
    ) as membership_end_at_utc
  from public.alpha_hunter_paper_execution_activation_v09 a
  left join public.alpha_hunter_paper_admission_halts_v09 h
    on h.activation_id=a.activation_id
  where a.activation_id='PAPER_EXECUTION_R9'
),
r10 as (
  select a.*
  from public.alpha_hunter_paper_execution_activation_v10 a
  where a.activation_id='PAPER_EXECUTION_R10'
)
select
  p.*,
  case
    when a10.activation_id is not null then a10.protocol_version
    when a9.activation_id is not null then a9.protocol_version
    else null
  end as horizon_protocol,
  case
    when a10.activation_id is not null then a10.scientific_fingerprint_sha256
    when a9.activation_id is not null then a9.scientific_fingerprint_sha256
    else null
  end as horizon_scientific_fingerprint_sha256,
  hh.previous_exit_observed_at_utc,
  coalesce(hh.horizon_integrity_failed,false) as horizon_integrity_failed,
  coalesce(hh.unresolved_protective_evidence,false) as unresolved_protective_evidence,
  coalesce(m9.fingerprints,array[]::text[]) as horizon_management_fingerprints
from public.alpha_hunter_paper_protection_open_v04 p
join public.alpha_hunter_paper_orders_v02 o
  on o.order_id=p.entry_order_id
left join r9 a9
  on o.successor_activation_id is null
 and o.submitted_at_utc>a9.activated_at_utc
 and o.submitted_at_utc<=a9.membership_end_at_utc
left join r10 a10
  on o.successor_activation_id=a10.activation_id
 and o.successor_spec_id=a10.spec_id
 and o.successor_scientific_fingerprint_sha256
     =a10.scientific_fingerprint_sha256
 and o.submitted_at_utc>a10.activated_at_utc
 and o.submitted_at_utc<=a10.admission_cutoff_at_utc
left join public.alpha_hunter_paper_horizon_history_v09 hh
  using(entry_order_id)
left join lateral (
  select array_agg(
    b.scientific_fingerprint_sha256
    order by b.scientific_fingerprint_sha256
  ) as fingerprints
  from public.alpha_hunter_r9_management_approvals_v01 b
  where b.entry_order_id=p.entry_order_id
    and a9.activation_id is not null
    and b.activation_id=a9.activation_id
) m9 on true;

revoke all on public.alpha_hunter_paper_protection_horizon_open_v09
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_protection_horizon_open_v09
to service_role;


-- R9 quality remains frozen to exact pre-halt membership. Future explicit
-- successors are excluded from R9 valid/quarantine evidence entirely.
create or replace view public.alpha_hunter_paper_completed_trade_quality_v09
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select
    a.*,
    least(
      a.admission_cutoff_at_utc,
      coalesce(h.halted_at_utc,a.admission_cutoff_at_utc)
    ) as membership_end_at_utc
  from public.alpha_hunter_paper_execution_activation_v09 a
  left join public.alpha_hunter_paper_admission_halts_v09 h
    on h.activation_id=a.activation_id
  where a.activation_id='PAPER_EXECUTION_R9'
  order by a.activated_at_utc desc
  limit 1
),
base as (
  select
    c.*,
    o.submitted_at_utc,
    o.quantity as ordered_quantity,
    d.strategy_id,
    d.strategy_name,
    d.evidence as decision_evidence,
    a.activated_at_utc as r9_activated_at_utc,
    a.release_git_commit as r9_release_git_commit,
    a.scientific_fingerprint_sha256 as r9_scientific_fingerprint_sha256,
    a.maximum_entry_age_minutes,
    a.maximum_monitoring_gap_minutes,
    a.required_run_source,
    a.required_runtime_role
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_orders_v02 o
    on o.order_id=c.entry_order_id
  join public.alpha_hunter_paper_decisions_v01 d
    on d.decision_id=c.decision_id
  cross join activation a
  where o.successor_activation_id is null
    and o.submitted_at_utc>a.activated_at_utc
    and o.submitted_at_utc<=a.membership_end_at_utc
),
fill_summary as (
  select
    f.order_id,
    count(*)::integer as entry_fill_count,
    sum(f.quantity) as total_entry_fill_quantity,
    min(f.filled_at_utc) as first_entry_fill_at_utc,
    max(f.filled_at_utc) as final_entry_fill_at_utc
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
),
partial_history as (
  select
    d.decision_id,
    count(*) filter(where e.state='PARTIALLY_FILLED')::integer
      as partial_fill_state_count
  from public.alpha_hunter_paper_decisions_v01 d
  left join public.alpha_hunter_paper_events_v01 e using(decision_id)
  group by d.decision_id
),
protection_start as (
  select
    p.entry_order_id,
    min(p.created_at_utc) as protection_created_at_utc
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id
),
timeline as (
  select
    b.entry_order_id,
    ps.protection_created_at_utc as observed_at_utc
  from base b
  join protection_start ps using(entry_order_id)

  union all

  select
    b.entry_order_id,
    a.observed_at_utc
  from base b
  join public.alpha_hunter_paper_exit_attempts_v04 a using(entry_order_id)

  union all

  select
    b.entry_order_id,
    b.closed_at_utc
  from base b
),
gaps as (
  select
    entry_order_id,
    observed_at_utc,
    extract(epoch from (
      observed_at_utc
      - lag(observed_at_utc) over(
          partition by entry_order_id
          order by observed_at_utc
        )
    ))/60.0 as monitoring_gap_minutes
  from timeline
),
monitoring as (
  select
    entry_order_id,
    max(monitoring_gap_minutes) as maximum_monitoring_gap_minutes_observed
  from gaps
  group by entry_order_id
)
select
  b.*,
  fs.entry_fill_count,
  fs.total_entry_fill_quantity,
  fs.first_entry_fill_at_utc,
  fs.final_entry_fill_at_utc,
  ph.partial_fill_state_count,
  m.maximum_monitoring_gap_minutes_observed,
  extract(epoch from (
    fs.final_entry_fill_at_utc-b.submitted_at_utc
  ))/60.0 as entry_fill_age_minutes,

  (
    coalesce(
      (b.decision_evidence->'paper_authority_source_gate'->>'passed')::boolean,
      false
    )
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'->>'observed_run_source',
      ''
    )=b.required_run_source
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'->>'observed_runtime_role',
      ''
    )=b.required_runtime_role
  ) as canonical_paper_authority_source_valid,

  (
    coalesce(
      b.decision_evidence->'validation_identity'
        ->>'scientific_fingerprint_sha256',
      ''
    )=b.r9_scientific_fingerprint_sha256
  ) as scientific_fingerprint_match,

  (
    coalesce(fs.entry_fill_count,0)=1
    and abs(
      coalesce(fs.total_entry_fill_quantity,0)-b.ordered_quantity
    )<=0.000000000001
    and coalesce(ph.partial_fill_state_count,0)=0
  ) as all_or_none_entry_valid,

  (
    fs.final_entry_fill_at_utc is not null
    and extract(epoch from (
      fs.final_entry_fill_at_utc-b.submitted_at_utc
    ))/60.0<=b.maximum_entry_age_minutes
  ) as entry_freshness_valid,

  (
    m.maximum_monitoring_gap_minutes_observed is not null
    and m.maximum_monitoring_gap_minutes_observed
        <=b.maximum_monitoring_gap_minutes
  ) as monitoring_cadence_valid,

  false as live_money_claim_permitted,
  false as production_promotion_permitted
from base b
left join fill_summary fs on fs.order_id=b.entry_order_id
left join partial_history ph on ph.decision_id=b.decision_id
left join monitoring m on m.entry_order_id=b.entry_order_id;



create or replace view public.alpha_hunter_paper_completed_trade_quality_v10
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_activation_v10 a
  where a.activation_id='PAPER_EXECUTION_R10'
  limit 1
),
base as (
  select
    c.*,
    o.submitted_at_utc,
    o.quantity as ordered_quantity,
    o.successor_activation_id,
    o.successor_spec_id,
    o.successor_scientific_fingerprint_sha256,
    o.successor_source_run_id,
    d.strategy_id,
    d.strategy_name,
    d.run_id as decision_run_id,
    d.evidence as decision_evidence,
    a.activated_at_utc as r10_activated_at_utc,
    a.admission_cutoff_at_utc as r10_admission_cutoff_at_utc,
    a.release_git_commit as r10_release_git_commit,
    a.scientific_fingerprint_sha256 as r10_scientific_fingerprint_sha256,
    a.maximum_entry_age_minutes,
    a.maximum_monitoring_gap_minutes,
    a.required_run_source,
    a.required_runtime_role
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_orders_v02 o
    on o.order_id=c.entry_order_id
  join public.alpha_hunter_paper_decisions_v01 d
    on d.decision_id=c.decision_id
   and d.run_id=o.successor_source_run_id
  join activation a
    on o.successor_activation_id=a.activation_id
   and o.successor_spec_id=a.spec_id
   and o.successor_scientific_fingerprint_sha256
       =a.scientific_fingerprint_sha256
  where o.submitted_at_utc>a.activated_at_utc
    and o.submitted_at_utc<=a.admission_cutoff_at_utc
),
fill_summary as (
  select
    f.order_id,
    count(*)::integer as entry_fill_count,
    sum(f.quantity) as total_entry_fill_quantity,
    min(f.filled_at_utc) as first_entry_fill_at_utc,
    max(f.filled_at_utc) as final_entry_fill_at_utc
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
),
partial_history as (
  select
    d.decision_id,
    count(*) filter(where e.state='PARTIALLY_FILLED')::integer
      as partial_fill_state_count
  from public.alpha_hunter_paper_decisions_v01 d
  left join public.alpha_hunter_paper_events_v01 e using(decision_id)
  group by d.decision_id
),
protection_start as (
  select
    p.entry_order_id,
    min(p.created_at_utc) as protection_created_at_utc
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id
),
timeline as (
  select b.entry_order_id,ps.protection_created_at_utc as observed_at_utc
  from base b
  join protection_start ps using(entry_order_id)

  union all

  select b.entry_order_id,a.observed_at_utc
  from base b
  join public.alpha_hunter_paper_exit_attempts_v04 a using(entry_order_id)

  union all

  select b.entry_order_id,b.closed_at_utc
  from base b
),
gaps as (
  select
    entry_order_id,
    observed_at_utc,
    extract(epoch from (
      observed_at_utc-lag(observed_at_utc) over(
        partition by entry_order_id order by observed_at_utc
      )
    ))/60.0 as monitoring_gap_minutes
  from timeline
),
monitoring as (
  select
    entry_order_id,
    max(monitoring_gap_minutes) as maximum_monitoring_gap_minutes_observed
  from gaps
  group by entry_order_id
),
history as (
  select
    h.entry_order_id,
    h.horizon_integrity_failed,
    h.unresolved_protective_evidence
  from public.alpha_hunter_paper_horizon_history_v09 h
)
select
  b.*,
  fs.entry_fill_count,
  fs.total_entry_fill_quantity,
  fs.first_entry_fill_at_utc,
  fs.final_entry_fill_at_utc,
  ph.partial_fill_state_count,
  m.maximum_monitoring_gap_minutes_observed,
  extract(epoch from (
    fs.final_entry_fill_at_utc-b.submitted_at_utc
  ))/60.0 as entry_fill_age_minutes,

  (
    b.successor_activation_id='PAPER_EXECUTION_R10'
    and b.successor_spec_id is not null
    and b.successor_scientific_fingerprint_sha256
        =b.r10_scientific_fingerprint_sha256
    and b.successor_source_run_id=b.decision_run_id
  ) as explicit_r10_membership_valid,

  (
    coalesce(
      (b.decision_evidence->'paper_authority_source_gate'->>'passed')::boolean,
      false
    )
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'
        ->>'observed_run_source',''
    )=b.required_run_source
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'
        ->>'observed_runtime_role',''
    )=b.required_runtime_role
  ) as canonical_paper_authority_source_valid,

  (
    coalesce(
      b.decision_evidence->'validation_identity'
        ->>'scientific_fingerprint_sha256',''
    )=b.r10_scientific_fingerprint_sha256
    and b.successor_scientific_fingerprint_sha256
        =b.r10_scientific_fingerprint_sha256
  ) as scientific_fingerprint_match,

  (
    coalesce(fs.entry_fill_count,0)=1
    and abs(
      coalesce(fs.total_entry_fill_quantity,0)-b.ordered_quantity
    )<=0.000000000001
    and coalesce(ph.partial_fill_state_count,0)=0
  ) as all_or_none_entry_valid,

  (
    fs.final_entry_fill_at_utc is not null
    and extract(epoch from (
      fs.final_entry_fill_at_utc-b.submitted_at_utc
    ))/60.0<=b.maximum_entry_age_minutes
  ) as entry_freshness_valid,

  (
    m.maximum_monitoring_gap_minutes_observed is not null
    and m.maximum_monitoring_gap_minutes_observed
        <=b.maximum_monitoring_gap_minutes
  ) as monitoring_cadence_valid,

  (
    not coalesce(h.horizon_integrity_failed,false)
    and not coalesce(h.unresolved_protective_evidence,false)
  ) as horizon_integrity_valid,

  (
    b.closed_at_utc is not null
    and fs.final_entry_fill_at_utc is not null
    and b.closed_at_utc>=fs.final_entry_fill_at_utc
    and (
      b.exit_reason is distinct from 'HORIZON_24H'
      or b.closed_at_utc between
         fs.final_entry_fill_at_utc+interval '24 hours'
         and fs.final_entry_fill_at_utc+interval '24 hours 35 minutes'
    )
  ) as terminal_exit_contract_valid,

  false as live_money_claim_permitted,
  false as production_promotion_permitted
from base b
left join fill_summary fs on fs.order_id=b.entry_order_id
left join partial_history ph on ph.decision_id=b.decision_id
left join monitoring m on m.entry_order_id=b.entry_order_id
left join history h on h.entry_order_id=b.entry_order_id;

revoke all on public.alpha_hunter_paper_completed_trade_quality_v10
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trade_quality_v10
to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_valid_v10
with (security_invoker=true,security_barrier=true)
as
select *
from public.alpha_hunter_paper_completed_trade_quality_v10
where explicit_r10_membership_valid
  and canonical_paper_authority_source_valid
  and scientific_fingerprint_match
  and all_or_none_entry_valid
  and entry_freshness_valid
  and monitoring_cadence_valid
  and horizon_integrity_valid
  and terminal_exit_contract_valid;

revoke all on public.alpha_hunter_paper_completed_trades_valid_v10
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_valid_v10
to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_quarantine_v10
with (security_invoker=true,security_barrier=true)
as
select
  q.*,
  array_remove(array[
    case when not explicit_r10_membership_valid
      then 'R10_EXPLICIT_MEMBERSHIP_INVALID' end,
    case when not canonical_paper_authority_source_valid
      then 'NON_CANONICAL_PAPER_AUTHORITY_SOURCE' end,
    case when not scientific_fingerprint_match
      then 'SCIENTIFIC_FINGERPRINT_MISMATCH' end,
    case when not all_or_none_entry_valid
      then 'ENTRY_NOT_ALL_OR_NONE' end,
    case when not entry_freshness_valid
      then 'ENTRY_STALE_OVER_35M' end,
    case when not monitoring_cadence_valid
      then 'PROTECTIVE_MONITORING_GAP_OVER_35M' end,
    case when not horizon_integrity_valid
      then 'HORIZON_INTEGRITY_FAILED' end,
    case when not terminal_exit_contract_valid
      then 'TERMINAL_EXIT_CONTRACT_INVALID' end
  ],null) as quarantine_reasons
from public.alpha_hunter_paper_completed_trade_quality_v10 q
where not (
  explicit_r10_membership_valid
  and canonical_paper_authority_source_valid
  and scientific_fingerprint_match
  and all_or_none_entry_valid
  and entry_freshness_valid
  and monitoring_cadence_valid
  and horizon_integrity_valid
  and terminal_exit_contract_valid
);

revoke all on public.alpha_hunter_paper_completed_trades_quarantine_v10
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_quarantine_v10
to service_role;


create or replace view public.alpha_hunter_paper_cohort_members_v10
with (security_invoker=true,security_barrier=true)
as
select
  a.activation_id,
  a.spec_id,
  o.order_id,
  o.decision_id,
  o.symbol,
  o.direction,
  o.submitted_at_utc,
  o.successor_source_run_id,
  o.successor_scientific_fingerprint_sha256,
  le.state as latest_state,
  f.entry_completed_at_utc,
  x.filled_at_utc as closed_at_utc,
  q.net_r_ex_funding,
  q.paper_net_pnl_ex_funding,
  coalesce(q.entry_order_id is not null,false) as completed_quality_valid,
  (
    coalesce(h.horizon_integrity_failed,false)
    or coalesce(h.unresolved_protective_evidence,false)
    or (
      f.entry_completed_at_utc is not null
      and coalesce(x.filled_at_utc,clock_timestamp())
          >f.entry_completed_at_utc+interval '24 hours 35 minutes'
    )
  ) as horizon_integrity_failed,
  (
    (le.state in ('EXPIRED','CANCELLED') and coalesce(f.filled_quantity,0)=0)
    or x.exit_fill_id is not null
  ) as terminal_reconciled
from public.alpha_hunter_paper_execution_activation_v10 a
join public.alpha_hunter_paper_orders_v02 o
  on o.successor_activation_id=a.activation_id
 and o.successor_spec_id=a.spec_id
 and o.successor_scientific_fingerprint_sha256
     =a.scientific_fingerprint_sha256
 and o.submitted_at_utc>a.activated_at_utc
 and o.submitted_at_utc<=a.admission_cutoff_at_utc
left join lateral (
  select e.state
  from public.alpha_hunter_paper_events_v01 e
  where e.decision_id=o.decision_id
  order by e.sequence desc,e.created_at desc
  limit 1
) le on true
left join lateral (
  select
    max(v.filled_at_utc) as entry_completed_at_utc,
    sum(v.quantity) as filled_quantity
  from public.alpha_hunter_paper_fills_v02 v
  where v.order_id=o.order_id
) f on true
left join public.alpha_hunter_paper_exit_fills_v04 x
  on x.entry_order_id=o.order_id
left join public.alpha_hunter_paper_completed_trades_valid_v10 q
  on q.entry_order_id=o.order_id
left join public.alpha_hunter_paper_horizon_history_v09 h
  on h.entry_order_id=o.order_id;

revoke all on public.alpha_hunter_paper_cohort_members_v10
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_cohort_members_v10
to service_role;


create or replace view public.alpha_hunter_paper_profitability_status_v10
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select
    a.*,
    s.minimum_test_days,
    s.minimum_completed_paper_trades,
    s.confidence_z,
    s.require_validated_cost_model
  from public.alpha_hunter_paper_execution_activation_v10 a
  join public.alpha_hunter_profitability_test_specs_v01 s using(spec_id)
  where a.activation_id='PAPER_EXECUTION_R10'
),
totals as (
  select
    a.spec_id,
    a.activated_at_utc,
    a.admission_cutoff_at_utc,
    a.minimum_test_days,
    a.minimum_completed_paper_trades,
    a.confidence_z,
    a.require_validated_cost_model,
    count(m.order_id) as admitted_orders,
    count(*) filter(
      where m.order_id is not null
        and not coalesce(m.terminal_reconciled,false)
    ) as unresolved_orders,
    count(*) filter(
      where m.horizon_integrity_failed
        or (m.closed_at_utc is not null and not m.completed_quality_valid)
    ) as integrity_failed_orders,
    count(*) filter(
      where m.closed_at_utc is not null
        and m.completed_quality_valid
        and not m.horizon_integrity_failed
    ) as completed_paper_trades,
    avg(m.net_r_ex_funding) filter(
      where m.completed_quality_valid and not m.horizon_integrity_failed
    ) as avg_net_r,
    stddev_samp(m.net_r_ex_funding) filter(
      where m.completed_quality_valid and not m.horizon_integrity_failed
    ) as sd_net_r,
    sum(m.net_r_ex_funding) filter(
      where m.completed_quality_valid
        and not m.horizon_integrity_failed
        and m.net_r_ex_funding>0
    )/
    nullif(abs(sum(m.net_r_ex_funding) filter(
      where m.completed_quality_valid
        and not m.horizon_integrity_failed
        and m.net_r_ex_funding<0
    )),0) as net_profit_factor
  from activation a
  left join public.alpha_hunter_paper_cohort_members_v10 m using(spec_id)
  group by
    a.spec_id,a.activated_at_utc,a.admission_cutoff_at_utc,
    a.minimum_test_days,a.minimum_completed_paper_trades,
    a.confidence_z,a.require_validated_cost_model
),
runtime as (
  select
    a.spec_id,
    count(p.run_id) as real_scans_since_registration,
    max(p.collected_at_utc) as latest_live_scan_at_utc,
    count(*) filter(
      where p.run_id is not null
        and (
          p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
            is distinct from a.scientific_fingerprint_sha256
          or p.payload->'validation_identity'->>'runtime_role'
            is distinct from a.required_runtime_role
        )
    ) as identity_drift_scans
  from public.alpha_hunter_paper_execution_activation_v10 a
  left join public.alpha_hunter_snapshots p
    on p.collected_at_utc>a.activated_at_utc
   and p.collected_at_utc<=a.admission_cutoff_at_utc
   and p.payload->'validation_identity'->>'run_source'=a.required_run_source
  where a.activation_id='PAPER_EXECUTION_R10'
  group by a.spec_id
),
stats as (
  select
    t.*,
    r.real_scans_since_registration,
    r.latest_live_scan_at_utc,
    r.identity_drift_scans,
    extract(epoch from(clock_timestamp()-t.activated_at_utc))/86400
      as test_days_elapsed,
    t.avg_net_r
      -t.confidence_z*t.sd_net_r/
       nullif(sqrt(t.completed_paper_trades::double precision),0)
      as net_r_lower_bound,
    (
      coalesce(c.full_cost_validation_evidence_complete,false)
      and coalesce(c.cost_model_activation_permitted,false)
      and coalesce(c.realistic_net_r_claim_permitted,false)
    ) as cost_validated
  from totals t
  join runtime r using(spec_id)
  left join public.alpha_hunter_execution_cost_validation_readiness_v04 c
    on true
),
verdict as (
  select
    s.*,
    case
      when exists(
        select 1
        from public.alpha_hunter_paper_admission_halts_v10 h
        where h.activation_id='PAPER_EXECUTION_R10'
      ) then 'BLOCKED_ADMISSION_HALTED'
      when integrity_failed_orders>0
        then 'BLOCKED_SUCCESSOR_INTEGRITY'
      when identity_drift_scans>0
        then 'BLOCKED_SUCCESSOR_IDENTITY_DRIFT'
      when clock_timestamp()<=admission_cutoff_at_utc
       and (
         latest_live_scan_at_utc is null
         or latest_live_scan_at_utc<clock_timestamp()-interval '35 minutes'
       ) then 'BLOCKED_CANONICAL_SCAN_STALE'
      when clock_timestamp()<=admission_cutoff_at_utc
        then 'RUNNING_MINIMUM_DURATION_NOT_MET'
      when unresolved_orders>0
        then 'RUNNING_ADMITTED_ORDERS_UNRESOLVED'
      when completed_paper_trades<minimum_completed_paper_trades
        then 'INSUFFICIENT_COMPLETED_SAMPLE_AT_FROZEN_CUT'
      when require_validated_cost_model and not cost_validated
        then 'BLOCKED_VALIDATED_COST_MODEL_MISSING'
      when net_r_lower_bound>0 and coalesce(net_profit_factor,0)>1
        then 'PAPER_EVIDENCE_PASS'
      else 'PAPER_PROFITABILITY_NOT_DEMONSTRATED'
    end as profitability_status
  from stats s
)
select
  v.*,
  clock_timestamp() as evaluated_at_utc,
  case
    when profitability_status like 'BLOCKED_%' then 'BLOCKED'
    else 'EVIDENCE_COLLECTION'
  end as operational_status,
  profitability_status as verdict,
  array_remove(array[
    case when require_validated_cost_model and not cost_validated
      then 'VALIDATED_EXECUTION_COST_MODEL_MISSING' end,
    case when integrity_failed_orders>0
      then 'SUCCESSOR_INTEGRITY_FAILURE' end,
    case when unresolved_orders>0
      then 'ADMITTED_ORDERS_UNRESOLVED' end,
    case when identity_drift_scans>0
      then 'SUCCESSOR_SCIENTIFIC_IDENTITY_DRIFT' end,
    case when profitability_status='BLOCKED_CANONICAL_SCAN_STALE'
      then 'LIVE_SCAN_STALE' end
  ],null) as blockers,
  true as paper_only,
  false as trade_permission,
  false as exchange_authority,
  false as production_promotion_permitted,
  false as live_money_claim_permitted,
  'NONE'::text as order_path,
  'realtime-test-engine-r10-horizon-v0.1'::text as engine_version,
  jsonb_build_object(
    'all_admitted_orders',admitted_orders,
    'unresolved_orders',unresolved_orders,
    'integrity_failed_orders',integrity_failed_orders,
    'admission_cutoff_at_utc',admission_cutoff_at_utc
  ) as source_status
from verdict v;

revoke all on public.alpha_hunter_paper_profitability_status_v10
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_profitability_status_v10
to service_role;


-- Replace the scaffold owner activation with one atomic execution +
-- cadence + profitability activation. Any failure rolls the statement back.
create or replace function private.alpha_hunter_activate_r10_executed_paper_v01(
  p_registration_id text,
  p_verification_id text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  r public.alpha_hunter_r10_preregistrations_v01%rowtype;
  v public.alpha_hunter_r10_runtime_verifications_v01%rowtype;
  s public.alpha_hunter_profitability_test_specs_v01%rowtype;
  p public.alpha_hunter_snapshots%rowtype;
  existing public.alpha_hunter_paper_execution_activation_v10%rowtype;
  open_r9 integer:=0;
  after_halt integer:=0;
  current_protected integer:=0;
  current_r9_cohort integer:=0;
  current_integrity_failures integer:=0;
  current_trade_permission boolean:=false;
  current_exchange_authority boolean:=false;
  current_order_path_all_none boolean:=true;
  existing_profit integer:=0;
  existing_cadence integer:=0;
  valid_symbols integer:=0;
  strategy_rows integer:=0;
  microstructure_rows integer:=0;
  closed_rows integer:=0;
  previous_source text:='NONE';
  catalyst_version text:='';
  config_sha text:='';
  activated_at timestamptz;
begin
  if p_registration_id<>'PAPER_EXECUTION_R10' then
    raise exception 'R10 registration identity mismatch';
  end if;

  select * into r
  from public.alpha_hunter_r10_preregistrations_v01
  where registration_id=p_registration_id;

  if r.registration_id is null then
    raise exception 'R10 preregistration is missing';
  end if;

  select * into v
  from public.alpha_hunter_r10_runtime_verifications_v01
  where verification_id=p_verification_id
    and registration_id=r.registration_id
    and spec_id=r.spec_id;

  if v.verification_id is null then
    raise exception
      'R10 runtime verification is missing or does not match preregistration';
  end if;

  select * into s
  from public.alpha_hunter_profitability_test_specs_v01
  where spec_id=r.spec_id;

  if s.spec_id is null then
    raise exception 'R10 profitability spec is missing';
  end if;

  if s.scientific_role<>'SUCCESSOR_EXECUTED_PAPER_24H_R10'
     or s.protocol_version<>r.protocol_version
     or s.required_strategy_count<>r.required_strategy_count
     or s.required_minimum_rr<>r.required_minimum_rr
     or s.evaluation_horizon_hours<>r.evaluation_horizon_hours
     or s.minimum_test_days<>r.minimum_test_days
     or s.minimum_completed_paper_trades<>r.minimum_completed_paper_trades
     or s.confidence_z<>r.confidence_z
     or not s.require_validated_cost_model
     or not s.shadow_only
     or s.trade_permission
     or s.production_promotion_permitted
     or s.order_path<>'NONE'
     or s.required_run_source<>r.required_run_source
     or s.frozen_git_commit<>r.frozen_git_commit
     or s.frozen_scientific_fingerprint_sha256
        <>r.frozen_scientific_fingerprint_sha256
  then
    raise exception 'R10 frozen spec does not exactly match preregistration';
  end if;

  if s.preregistered_at_utc<>r.preregistered_at_utc then
    raise exception 'R10 spec/preregistration time boundary mismatch';
  end if;

  select * into p
  from public.alpha_hunter_snapshots
  where run_id=v.run_id;

  if p.run_id is null then
    raise exception 'R10 verified canonical snapshot is missing';
  end if;

  previous_source:=coalesce(
    p.payload->'previous_snapshot_context'->>'source','NONE'
  );
  catalyst_version:=coalesce(
    p.payload->'catalyst_summary'->>'version',''
  );
  config_sha:=coalesce(
    p.payload->'validation_identity'->>'config_sha256',''
  );

  if p.collected_at_utc<>v.scan_collected_at_utc
     or p.collected_at_utc<=r.preregistered_at_utc
     or coalesce(p.payload->'validation_identity'->>'git_commit','')
        <>r.frozen_git_commit
     or coalesce(
       p.payload->'validation_identity'->>'scientific_fingerprint_sha256',''
     )<>r.frozen_scientific_fingerprint_sha256
     or coalesce(p.payload->'validation_identity'->>'run_source','')
        <>r.required_run_source
     or coalesce(p.payload->'validation_identity'->>'runtime_role','')
        <>r.required_runtime_role
     or previous_source='NONE'
     or coalesce(p.payload->'previous_snapshot_context'->>'run_id','')=''
     or coalesce(
       nullif(
         p.payload->'multi_strategy_summary'->>'configured_strategy_count',''
       )::integer,0
     )<>r.required_strategy_count
     or coalesce(
       nullif(p.payload->'multi_strategy_summary'->>'total_evaluations','')
         ::integer,0
     )<=0
     or catalyst_version<>'0.2'
     or config_sha=''
  then
    raise exception
      'R10 verified snapshot does not satisfy frozen canonical identity/context';
  end if;

  if v.git_commit<>r.frozen_git_commit
     or v.scientific_fingerprint_sha256
        <>r.frozen_scientific_fingerprint_sha256
     or v.run_source<>r.required_run_source
     or v.runtime_role<>r.required_runtime_role
     or v.previous_snapshot_source='NONE'
     or v.previous_snapshot_run_id=''
     or v.configured_strategy_count<>r.required_strategy_count
     or v.total_strategy_evaluations<=0
     or v.unprotected_open_positions<>0
     or v.r9_admission_open_rows<>0
     or v.orders_after_r9_halt<>0
     or v.r9_cohort_rows<0
     or v.r9_integrity_failed_orders<0
     or v.trade_permission_any
     or v.exchange_authority_any
     or not v.order_path_all_none
     or v.r10_spec_rows<>1
     or v.r10_activation_rows_before<>0
  then
    raise exception 'R10 runtime verification fails owner activation contract';
  end if;

  select count(*) into open_r9
  from public.alpha_hunter_paper_admission_open_v09;

  if open_r9<>0 then
    raise exception 'R9 admission is unexpectedly open';
  end if;

  select count(*) into after_halt
  from public.alpha_hunter_paper_orders_v02 o
  cross join (
    select halted_at_utc
    from public.alpha_hunter_paper_admission_halts_v09
    where activation_id='PAPER_EXECUTION_R9'
  ) h
  where o.submitted_at_utc>h.halted_at_utc;

  if after_halt<>0 then
    raise exception 'Orders exist after R9 halt; refusing R10 activation';
  end if;

  select * into existing
  from public.alpha_hunter_paper_execution_activation_v10
  where activation_id=r.registration_id;

  select count(*) into existing_profit
  from public.alpha_hunter_profitability_test_activations_v01
  where spec_id=r.spec_id;

  select count(*) into existing_cadence
  from public.alpha_hunter_profitability_cadence_contract_v01
  where spec_id=r.spec_id;

  if existing.activation_id is not null
     or existing_profit<>0
     or existing_cadence<>0
  then
    raise exception
      'R10 activation/cadence/profitability state already exists or is partial';
  end if;

  activated_at:=clock_timestamp();

  if v.verified_at_utc<v.scan_collected_at_utc
     or activated_at<=v.verified_at_utc
     or activated_at-v.verified_at_utc
        >make_interval(mins=>r.maximum_activation_verification_age_minutes)
     or activated_at-v.scan_collected_at_utc
        >make_interval(mins=>r.maximum_monitoring_gap_minutes)
  then
    raise exception 'R10 activation verification is stale or temporally invalid';
  end if;

  select
    count(*)::integer,
    coalesce(bool_or(trade_permission),false),
    coalesce(bool_or(exchange_authority),false),
    coalesce(bool_and(order_path='NONE'),true)
  into
    current_protected,
    current_trade_permission,
    current_exchange_authority,
    current_order_path_all_none
  from public.alpha_hunter_paper_protection_horizon_open_v09;

  select count(*)::integer into current_r9_cohort
  from public.alpha_hunter_paper_cohort_members_v09;

  select coalesce(max(integrity_failed_orders),0)::integer
  into current_integrity_failures
  from public.alpha_hunter_paper_profitability_status_v09;

  if current_protected<>v.protected_open_positions
     or current_r9_cohort<>v.r9_cohort_rows
     or current_integrity_failures<>v.r9_integrity_failed_orders
     or current_trade_permission
     or current_exchange_authority
     or not current_order_path_all_none
  then
    raise exception 'R10 production state changed after runtime verification';
  end if;

  select
    count(*) filter(where c.error is null),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(c.payload->'multi_strategy_engine')='object'
    ),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(c.payload->'microstructure')='object'
    ),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(
          c.payload->'timeframes'->'1H'->'last_closed_candle'
        )='object'
    )
  into valid_symbols,strategy_rows,microstructure_rows,closed_rows
  from public.alpha_hunter_symbol_snapshots c
  where c.run_id=v.run_id;

  if valid_symbols=0
     or strategy_rows<>valid_symbols
     or microstructure_rows<>valid_symbols
     or closed_rows<>valid_symbols
  then
    raise exception 'R10 verified canonical child evidence is incomplete';
  end if;

  insert into public.alpha_hunter_paper_execution_activation_v10(
    activation_id,spec_id,protocol_version,activated_at_utc,
    runtime_verified_at_utc,admission_cutoff_at_utc,
    release_git_commit,scientific_fingerprint_sha256,
    maximum_entry_age_minutes,maximum_monitoring_gap_minutes,
    horizon_hours,maximum_horizon_lag_minutes,
    required_run_source,required_runtime_role,evidence,
    paper_only,exchange_authority,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    r.registration_id,r.spec_id,r.protocol_version,activated_at,
    v.verified_at_utc,
    activated_at+(r.admission_window_days||' days')::interval,
    r.frozen_git_commit,r.frozen_scientific_fingerprint_sha256,
    r.maximum_entry_age_minutes,r.maximum_monitoring_gap_minutes,
    r.evaluation_horizon_hours,r.maximum_horizon_lag_minutes,
    r.required_run_source,r.required_runtime_role,
    jsonb_build_object(
      'owner_only_activation',true,
      'atomic_r10_activation',true,
      'preregistration_id',r.registration_id,
      'verification_id',v.verification_id,
      'verified_run_id',v.run_id,
      'verified_scan_at_utc',v.scan_collected_at_utc,
      'previous_snapshot_source',v.previous_snapshot_source,
      'previous_snapshot_run_id',v.previous_snapshot_run_id,
      'verified_protected_open_positions',v.protected_open_positions,
      'verified_r9_cohort_rows',v.r9_cohort_rows,
      'verified_r9_integrity_failed_orders',v.r9_integrity_failed_orders,
      'historical_rows_reused',false,
      'r9_reopened',false
    ),
    true,false,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_cadence_contract_v01(
    spec_id,baseline_not_before_utc,
    expected_frequency_minutes,minimum_interval_minutes,
    maximum_interval_minutes,expected_schedule,
    no_manual_scans_after_baseline,scientific_role,
    frozen,trade_permission,production_promotion_permitted,order_path
  ) values (
    r.spec_id,
    activated_at,
    20,15,35,
    'RENDER_CRON_ALIGNED_00_20_40',
    true,
    'SEALED_SCAN_CADENCE_CONTRACT_R10',
    true,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_test_activations_v01(
    spec_id,baseline_run_id,started_at_utc,
    baseline_config_sha256,baseline_git_commit,
    baseline_previous_snapshot_source,baseline_catalyst_version,
    baseline_symbol_rows,baseline_strategy_rows,
    baseline_microstructure_rows,baseline_closed_candle_rows,
    activation_checks,baseline_scientific_fingerprint_sha256,
    scientific_role,shadow_only,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    r.spec_id,
    v.run_id,
    activated_at,
    config_sha,
    r.frozen_git_commit,
    previous_source,
    catalyst_version,
    valid_symbols,
    strategy_rows,
    microstructure_rows,
    closed_rows,
    jsonb_build_object(
      'atomic_r10_activation',true,
      'paper_execution_activation_aligned',true,
      'cadence_contract_aligned',true,
      'preregistration_boundary_ok',
        v.scan_collected_at_utc>r.preregistered_at_utc,
      'identity_mode','SCIENTIFIC_FINGERPRINT',
      'scientific_fingerprint_ok',true,
      'git_anchor_commit',r.frozen_git_commit,
      'baseline_observed_git_commit',
        p.payload->'validation_identity'->>'git_commit',
      'previous_context_ok',previous_source<>'NONE',
      'strategy_count_ok',true,
      'strategy_rows_complete',strategy_rows=valid_symbols,
      'microstructure_rows_complete',microstructure_rows=valid_symbols,
      'closed_candle_rows_complete',closed_rows=valid_symbols,
      'sample_source','alpha_hunter_paper_completed_trades_valid_v10',
      'quarantine_source','alpha_hunter_paper_completed_trades_quarantine_v10',
      'quarantine_nonzero_invalidates_cohort',true,
      'historical_rows_reused',false
    ),
    r.frozen_scientific_fingerprint_sha256,
    'SEALED_PROFITABILITY_ACTIVATION_R10_EXECUTED_PAPER',
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','ACTIVATED',
    'activation_id',r.registration_id,
    'spec_id',r.spec_id,
    'verified_run_id',v.run_id,
    'started_at_utc',activated_at,
    'scientific_fingerprint_sha256',
      r.frozen_scientific_fingerprint_sha256,
    'paper_only',true,
    'exchange_authority',false,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'live_money_claim_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function
private.alpha_hunter_activate_r10_executed_paper_v01(text,text)
from public,anon,authenticated,service_role;

commit;
