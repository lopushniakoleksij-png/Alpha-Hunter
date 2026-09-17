begin;

-- Alpha Hunter canonical execution-gate evidence v0.1.
-- Read-only provenance surface for PAPER/SHADOW authorization review.
-- It does not place orders, grant trade permission, activate policy versions,
-- or make LIVE execution available.

create or replace view public.alpha_hunter_execution_gate_evidence_v01
with (security_invoker=true)
as
with bound as (
  select
    s.stage_snapshot_id,
    s.control_run_id,
    s.source_run_id,
    s.source_bridge_id,
    s.source_signal_id,
    s.source_captured_at_utc,
    s.snapshot_at_utc,
    s.symbol,
    s.direction,
    s.stage_status,
    s.stage_eligible,
    s.threshold_set_id,
    s.threshold_status,
    s.candidate_entry,
    s.stop_price,
    s.target_price,
    s.stop_distance_pct,
    s.remaining_r,
    s.open_position_conflict,
    s.shadow_only as stage_shadow_only,
    s.trade_permission as stage_trade_permission,

    t.status as threshold_registry_status,
    t.validated_at_utc as threshold_validated_at_utc,
    t.activated_at_utc as threshold_activated_at_utc,
    t.model_version as threshold_model_version,
    t.evidence_reference as threshold_evidence_reference,
    t.shadow_only as threshold_shadow_only,
    t.trade_permission as threshold_trade_permission,

    ce.cost_evidence_id,
    ce.cost_model_id,
    ce.cost_model_status,
    ce.realistic_net_r,
    ce.realistic_net_r_status,
    ce.shadow_only as cost_evidence_shadow_only,
    ce.trade_permission as cost_evidence_trade_permission,
    cm.status as cost_model_registry_status,
    cm.validated_at_utc as cost_model_validated_at_utc,
    cm.activated_at_utc as cost_model_activated_at_utc,
    cm.model_version as cost_model_version,
    cm.evidence_reference as cost_model_evidence_reference,
    cm.shadow_only as cost_model_shadow_only,
    cm.trade_permission as cost_model_trade_permission,

    pr.risk_assessment_id,
    pr.risk_policy_id,
    pr.risk_policy_status,
    pr.account_snapshot_id,
    pr.account_state_status,
    pr.position_ledger_status,
    pr.risk_decision,
    pr.symbol_position_conflict,
    pr.aggregate_risk_complete,
    pr.blockers as risk_blockers,
    pr.shadow_only as risk_shadow_only,
    pr.trade_permission as risk_trade_permission,
    rp.status as risk_policy_registry_status,
    rp.validated_at_utc as risk_policy_validated_at_utc,
    rp.activated_at_utc as risk_policy_activated_at_utc,
    rp.model_version as risk_policy_model_version,
    rp.evidence_reference as risk_policy_evidence_reference,
    rp.shadow_only as risk_policy_shadow_only,
    rp.trade_permission as risk_policy_trade_permission,

    a.connection_status as account_connection_status,
    a.schema_validated as account_schema_validated,
    a.complete as account_complete,
    a.captured_at_utc as account_captured_at_utc,
    a.evidence as account_evidence,
    a.shadow_only as account_shadow_only,
    a.trade_permission as account_trade_permission,

    cp.scheduled_hour_utc,
    cp.finalized_at_utc,
    cp.overall_status as control_plane_status,
    cp.data_freshness_status,
    cp.safety_status,
    cp.release_version as control_plane_release_version,
    cp.production_execution_enabled,
    cp.research_trade_permission,

    u.observation_id as universe_observation_id,
    u.observed_at_utc as universe_observed_at_utc,
    u.selection_run_id as universe_selection_run_id,
    u.product_type,
    u.crypto_allowed,
    u.liquidity_pass,
    u.prefilter_eligible,
    u.measurement_quality as universe_measurement_quality,
    u.trade_permission as universe_trade_permission
  from public.alpha_hunter_money_entry_stage_snapshots s
  left join public.alpha_hunter_money_entry_threshold_sets t
    on t.threshold_set_id=s.threshold_set_id
  left join public.alpha_hunter_execution_cost_evidence ce
    on ce.stage_snapshot_id=s.stage_snapshot_id
  left join public.alpha_hunter_execution_cost_model_versions cm
    on cm.cost_model_id=ce.cost_model_id
  left join public.alpha_hunter_portfolio_risk_assessments pr
    on pr.stage_snapshot_id=s.stage_snapshot_id
  left join public.alpha_hunter_risk_policy_versions rp
    on rp.risk_policy_id=pr.risk_policy_id
  left join public.alpha_hunter_account_state_snapshots a
    on a.account_snapshot_id=pr.account_snapshot_id
  left join public.alpha_hunter_control_plane_runs cp
    on cp.control_run_id=s.control_run_id
  left join lateral (
    select ux.*
    from public.alpha_hunter_universe_hourly ux
    where ux.symbol=s.symbol
      and ux.selection_run_id=s.source_run_id
    order by ux.observed_at_utc desc,ux.created_at desc
    limit 1
  ) u on true
), checks as (
  select b.*,
    (
      b.control_run_id is not null
      and b.source_run_id is not null
      and b.cost_evidence_id is not null
      and b.risk_assessment_id is not null
      and b.account_snapshot_id is not null
      and b.universe_observation_id is not null
      and exists (
        select 1 from public.alpha_hunter_execution_cost_evidence ce2
        where ce2.cost_evidence_id=b.cost_evidence_id
          and ce2.control_run_id=b.control_run_id
          and ce2.source_run_id=b.source_run_id
          and ce2.stage_snapshot_id=b.stage_snapshot_id
          and ce2.symbol=b.symbol
          and ce2.direction=b.direction
      )
      and exists (
        select 1 from public.alpha_hunter_portfolio_risk_assessments pr2
        where pr2.risk_assessment_id=b.risk_assessment_id
          and pr2.control_run_id=b.control_run_id
          and pr2.source_run_id=b.source_run_id
          and pr2.stage_snapshot_id=b.stage_snapshot_id
          and pr2.cost_evidence_id=b.cost_evidence_id
          and pr2.symbol=b.symbol
          and pr2.direction=b.direction
          and pr2.account_snapshot_id=b.account_snapshot_id
      )
      and b.universe_selection_run_id=b.source_run_id
      and coalesce(b.account_evidence->>'canonical_run_id','')=b.source_run_id
    ) as source_binding_valid,
    (
      b.stage_eligible is true
      and b.stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED')
      and b.threshold_set_id is not null
      and b.threshold_registry_status='ACTIVE'
      and b.threshold_validated_at_utc is not null
      and b.threshold_activated_at_utc is not null
      and coalesce(b.threshold_evidence_reference,'{}'::jsonb)<>'{}'::jsonb
      and b.threshold_shadow_only is true
      and b.threshold_trade_permission is false
    ) as money_entry_gate_valid,
    (
      b.cost_evidence_id is not null
      and b.cost_model_id is not null
      and b.cost_model_status='ACTIVE_VALIDATED_COST_MODEL'
      and b.cost_model_registry_status='ACTIVE'
      and b.cost_model_validated_at_utc is not null
      and b.cost_model_activated_at_utc is not null
      and coalesce(b.cost_model_evidence_reference,'{}'::jsonb)<>'{}'::jsonb
      and b.realistic_net_r_status in ('VERIFIED_FULL_COST_PATH','VERIFIED_NET_R')
      and b.realistic_net_r is not null
      and b.cost_evidence_shadow_only is true
      and b.cost_evidence_trade_permission is false
      and b.cost_model_shadow_only is true
      and b.cost_model_trade_permission is false
    ) as cost_gate_valid,
    (
      b.risk_assessment_id is not null
      and b.risk_policy_id is not null
      and b.risk_policy_status='ACTIVE_VALIDATED_RISK_POLICY'
      and b.risk_policy_registry_status='ACTIVE'
      and b.risk_policy_validated_at_utc is not null
      and b.risk_policy_activated_at_utc is not null
      and coalesce(b.risk_policy_evidence_reference,'{}'::jsonb)<>'{}'::jsonb
      and b.risk_decision='ELIGIBLE_FOR_RISK_REVIEW'
      and b.account_state_status='CONNECTED_READ_ONLY_COMPLETE'
      and b.position_ledger_status='VERIFIED_SNAPSHOT'
      and b.symbol_position_conflict is false
      and b.aggregate_risk_complete is true
      and coalesce(jsonb_array_length(b.risk_blockers),0)=0
      and b.risk_shadow_only is true
      and b.risk_trade_permission is false
      and b.risk_policy_shadow_only is true
      and b.risk_policy_trade_permission is false
    ) as portfolio_risk_gate_valid,
    (
      b.account_snapshot_id is not null
      and b.account_connection_status='CONNECTED_READ_ONLY'
      and b.account_schema_validated is true
      and b.account_complete is true
      and coalesce(b.account_evidence->>'canonical_run_id','')=b.source_run_id
      and b.account_shadow_only is true
      and b.account_trade_permission is false
    ) as account_gate_valid,
    (
      b.universe_observation_id is not null
      and lower(coalesce(b.product_type,''))='usdt-futures'
      and b.crypto_allowed is true
      and b.liquidity_pass is true
      and b.universe_selection_run_id=b.source_run_id
      and b.universe_trade_permission is false
    ) as universe_gate_valid,
    (
      b.safety_status='PASS'
      and b.data_freshness_status='FRESH'
      and b.production_execution_enabled is false
      and b.research_trade_permission is false
      and exists (
        select 1 from public.alpha_hunter_control_plane_runs cp2
        where cp2.control_run_id=b.control_run_id
          and cp2.source_run_id=b.source_run_id
      )
    ) as control_plane_gate_valid,
    (
      b.stage_shadow_only is true and b.stage_trade_permission is false
      and b.cost_evidence_shadow_only is true and b.cost_evidence_trade_permission is false
      and b.risk_shadow_only is true and b.risk_trade_permission is false
      and b.account_shadow_only is true and b.account_trade_permission is false
      and b.universe_trade_permission is false
      and b.production_execution_enabled is false
      and b.research_trade_permission is false
    ) as shadow_safety_boundary_valid
  from bound b
), evaluated as (
  select c.*,
    to_jsonb(array_remove(array[
      case when c.source_binding_valid is not true then 'CANONICAL_SOURCE_BINDING_INVALID' end,
      case when c.money_entry_gate_valid is not true then 'MONEY_ENTRY_GATE_NOT_VALIDATED' end,
      case when c.cost_gate_valid is not true then 'EXECUTION_COST_GATE_NOT_VALIDATED' end,
      case when c.portfolio_risk_gate_valid is not true then 'PORTFOLIO_RISK_GATE_NOT_VALIDATED' end,
      case when c.account_gate_valid is not true then 'ACCOUNT_STATE_NOT_CANONICAL_VERIFIED' end,
      case when c.universe_gate_valid is not true then 'FUTURES_UNIVERSE_GATE_NOT_VERIFIED' end,
      case when c.control_plane_gate_valid is not true then 'CONTROL_PLANE_SAFETY_OR_FRESHNESS_BLOCK' end,
      case when c.shadow_safety_boundary_valid is not true then 'SHADOW_SAFETY_BOUNDARY_INVALID' end
    ]::text[],null)) as authorization_blockers
  from checks c
)
select
  md5('canonical-execution-gate-evidence-v0.1|'||e.stage_snapshot_id||'|'||coalesce(e.cost_evidence_id,'')||'|'||coalesce(e.risk_assessment_id,'')||'|'||coalesce(e.account_snapshot_id,'')||'|'||coalesce(e.universe_observation_id,'')) as execution_gate_evidence_id,
  'canonical-execution-gate-evidence-v0.1'::text as contract_version,
  e.*,
  (
    e.source_binding_valid
    and e.money_entry_gate_valid
    and e.cost_gate_valid
    and e.portfolio_risk_gate_valid
    and e.account_gate_valid
    and e.universe_gate_valid
    and e.control_plane_gate_valid
    and e.shadow_safety_boundary_valid
    and jsonb_array_length(e.authorization_blockers)=0
  ) as paper_authorization_eligible,
  false as live_authorization_eligible,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from evaluated e;

revoke all on public.alpha_hunter_execution_gate_evidence_v01 from public,anon,authenticated;
grant select on public.alpha_hunter_execution_gate_evidence_v01 to service_role;

commit;