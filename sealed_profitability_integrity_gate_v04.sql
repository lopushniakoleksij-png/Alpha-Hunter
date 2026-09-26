-- Alpha Hunter sealed profitability integrity gate v0.4
--
-- Conservative scientific guardrail:
-- a sealed profitability result cannot pass if its source-scoped cadence or
-- sample-integrity audit fails. This does not relax any economic threshold.
--
-- Output columns and trading authority remain unchanged.

create or replace view public.alpha_hunter_profitability_validation_status_v01
with (security_invoker=true,security_barrier=true)
as
with spec_activation as (
  select
    s.*,
    a.baseline_run_id,
    a.started_at_utc,
    a.baseline_config_sha256,
    a.baseline_git_commit,
    a.baseline_previous_snapshot_source,
    a.baseline_catalyst_version
  from public.alpha_hunter_profitability_test_specs_v01 s
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
),
drift as (
  select
    sa.spec_id,
    count(p.*) as post_start_scans,
    count(p.*) filter(
      where (
        coalesce(p.payload->'validation_identity'->>'git_commit','')
          <>sa.baseline_git_commit
        or coalesce(p.payload->'validation_identity'->>'config_sha256','')
          <>sa.baseline_config_sha256
      )
    ) as drift_scans
  from spec_activation sa
  left join public.alpha_hunter_snapshots p
    on sa.started_at_utc is not null
   and p.collected_at_utc>=sa.started_at_utc
   and p.payload->'validation_identity'->>'run_source'
      =sa.required_run_source
  group by sa.spec_id
),
econ as (
  select
    e.spec_id,
    count(*) as completed_paper_trades,
    avg(e.gross_r_pre_cost) as avg_gross_r,
    stddev_samp(e.gross_r_pre_cost) as sd_gross_r,
    avg(e.floor_adjusted_r) as avg_floor_adjusted_r,
    stddev_samp(e.floor_adjusted_r) as sd_floor_adjusted_r,
    avg(e.modeled_net_r) filter(where e.modeled_net_r is not null)
      as avg_modeled_net_r,
    stddev_samp(e.modeled_net_r) filter(where e.modeled_net_r is not null)
      as sd_modeled_net_r,
    count(*) filter(where e.modeled_net_r is not null)
      as modeled_net_trade_count,
    sum(e.floor_adjusted_r) filter(where e.floor_adjusted_r>0)
      /nullif(abs(sum(e.floor_adjusted_r) filter(where e.floor_adjusted_r<0)),0)
      as floor_profit_factor,
    sum(e.modeled_net_r) filter(where e.modeled_net_r>0)
      /nullif(abs(sum(e.modeled_net_r) filter(where e.modeled_net_r<0)),0)
      as modeled_net_profit_factor
  from public.alpha_hunter_strategy_paper_economics_v01 e
  group by e.spec_id
),
cost_status as (
  select
    cost_model_validated,
    realistic_net_r_claim_permitted,
    scientific_status,
    next_gate
  from public.alpha_hunter_execution_cost_floor_status_v01
  where cost_scope='ALL'
  limit 1
),
integrity as (
  select
    sa.spec_id,
    coalesce(ci.cadence_integrity_ok,false) as cadence_ok,
    coalesce(ci.cadence_integrity_status,'MISSING') as cadence_status,
    coalesce(si.sealed_sample_integrity_ok,false) as sample_integrity_ok,
    coalesce(si.sample_integrity_status,'MISSING') as sample_integrity_status
  from spec_activation sa
  left join public.alpha_hunter_profitability_cadence_integrity_v01 ci
    on ci.spec_id=sa.spec_id
  left join public.alpha_hunter_profitability_sample_integrity_v01 si
    on si.spec_id=sa.spec_id
)
select
  sa.spec_id,
  sa.protocol_version,
  sa.frozen_git_commit,
  sa.baseline_run_id,
  sa.started_at_utc,
  sa.minimum_test_days,
  sa.minimum_completed_paper_trades,
  case
    when sa.started_at_utc is null then 0.0
    else extract(epoch from (clock_timestamp()-sa.started_at_utc))/86400.0
  end as test_days_elapsed,
  coalesce(d.post_start_scans,0) as post_start_scans,
  coalesce(d.drift_scans,0) as identity_drift_scans,
  coalesce(e.completed_paper_trades,0) as completed_paper_trades,
  e.avg_gross_r,
  case
    when coalesce(e.completed_paper_trades,0)>=2
      then e.avg_gross_r
        - sa.confidence_z*e.sd_gross_r/sqrt(e.completed_paper_trades)
    else null
  end as gross_r_lower_95,
  e.avg_floor_adjusted_r,
  case
    when coalesce(e.completed_paper_trades,0)>=2
      then e.avg_floor_adjusted_r
        - sa.confidence_z*e.sd_floor_adjusted_r
          /sqrt(e.completed_paper_trades)
    else null
  end as floor_adjusted_r_lower_95,
  e.floor_profit_factor,
  coalesce(e.modeled_net_trade_count,0) as modeled_net_trade_count,
  e.avg_modeled_net_r,
  case
    when coalesce(e.modeled_net_trade_count,0)>=2
      then e.avg_modeled_net_r
        - sa.confidence_z*e.sd_modeled_net_r
          /sqrt(e.modeled_net_trade_count)
    else null
  end as modeled_net_r_lower_95,
  e.modeled_net_profit_factor,
  coalesce(cs.cost_model_validated,false) as cost_model_validated,
  coalesce(cs.realistic_net_r_claim_permitted,false)
    as realistic_net_r_claim_permitted,
  cs.scientific_status as cost_scientific_status,
  cs.next_gate as cost_next_gate,
  (sa.started_at_utc is not null) as test_activated,
  (
    sa.started_at_utc is not null
    and extract(epoch from (clock_timestamp()-sa.started_at_utc))/86400.0
      >=sa.minimum_test_days
  ) as duration_gate_met,
  (
    coalesce(e.completed_paper_trades,0)
      >=sa.minimum_completed_paper_trades
  ) as sample_gate_met,
  (coalesce(d.drift_scans,0)=0) as identity_drift_gate_met,
  (
    coalesce(i.cadence_ok,false)
    and coalesce(i.sample_integrity_ok,false)
    and coalesce(e.completed_paper_trades,0)
      >=sa.minimum_completed_paper_trades
    and e.avg_floor_adjusted_r is not null
    and e.avg_floor_adjusted_r
      - sa.confidence_z*e.sd_floor_adjusted_r
        /sqrt(e.completed_paper_trades) > 0
    and coalesce(e.floor_profit_factor,0)>1.0
  ) as conservative_floor_edge_gate_met,
  (
    coalesce(i.cadence_ok,false)
    and coalesce(i.sample_integrity_ok,false)
    and coalesce(e.modeled_net_trade_count,0)
      >=sa.minimum_completed_paper_trades
    and coalesce(cs.cost_model_validated,false)
    and coalesce(cs.realistic_net_r_claim_permitted,false)
    and e.avg_modeled_net_r is not null
    and e.avg_modeled_net_r
      - sa.confidence_z*e.sd_modeled_net_r
        /sqrt(e.modeled_net_trade_count) > 0
    and coalesce(e.modeled_net_profit_factor,0)>1.0
  ) as modeled_net_edge_gate_met,
  case
    when sa.started_at_utc is null
      then 'ARMED_WAITING_FOR_CLEAN_BASELINE'
    when coalesce(d.drift_scans,0)>0
      then 'INVALIDATED_BY_BUILD_OR_CONFIG_DRIFT'
    when not coalesce(i.cadence_ok,false)
      then 'INVALIDATED_BY_CADENCE_INTEGRITY'
    when not coalesce(i.sample_integrity_ok,false)
      then 'INVALIDATED_BY_SAMPLE_INTEGRITY'
    when extract(epoch from (clock_timestamp()-sa.started_at_utc))/86400.0
      <sa.minimum_test_days
      then 'RUNNING_MINIMUM_DURATION_NOT_MET'
    when coalesce(e.completed_paper_trades,0)
      <sa.minimum_completed_paper_trades
      then 'RUNNING_SAMPLE_NOT_MET'
    when not coalesce(cs.cost_model_validated,false)
      or not coalesce(cs.realistic_net_r_claim_permitted,false)
      then 'BLOCKED_NO_VALIDATED_REALISTIC_COST_MODEL'
    when not (
      e.avg_modeled_net_r
        - sa.confidence_z*e.sd_modeled_net_r
          /sqrt(e.modeled_net_trade_count) > 0
      and coalesce(e.modeled_net_profit_factor,0)>1.0
    ) then 'NO_POSITIVE_NET_EDGE_DEMONSTRATED'
    else 'POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_PAPER_TEST'
  end as profitability_test_status,
  false as live_money_claim_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  true as run_source_isolated
from spec_activation sa
left join drift d on d.spec_id=sa.spec_id
left join econ e on e.spec_id=sa.spec_id
left join cost_status cs on true
left join integrity i on i.spec_id=sa.spec_id;

revoke all on public.alpha_hunter_profitability_validation_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_validation_status_v01
  to service_role;
