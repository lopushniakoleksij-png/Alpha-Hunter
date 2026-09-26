-- Alpha Hunter sealed scientific fingerprint v0.1
--
-- Purpose:
--   Keep sealed forward tests stable across non-scientific UI/dashboard changes
--   while invalidating them for scanner, strategy, evidence SQL, config, or
--   runtime dependency changes.
--
-- Legacy specs with no frozen fingerprint retain the historical Git+config
-- identity rule. New specs can opt into scientific fingerprint identity.
--
-- Safety:
--   paper/shadow only; no strategy threshold, READY, order, or trade authority.

alter table public.alpha_hunter_profitability_test_specs_v01
  add column if not exists frozen_scientific_fingerprint_sha256 text;

alter table public.alpha_hunter_profitability_test_activations_v01
  add column if not exists baseline_scientific_fingerprint_sha256 text;

create index if not exists idx_ah_profitability_specs_science_fp_v01
  on public.alpha_hunter_profitability_test_specs_v01(
    frozen_scientific_fingerprint_sha256
  );

create or replace function private.alpha_hunter_try_activate_profitability_test_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec public.alpha_hunter_profitability_test_specs_v01%rowtype;
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_valid_symbols integer;
  v_strategy_rows integer;
  v_micro_rows integer;
  v_closed_rows integer;
  v_previous_source text;
  v_previous_run_source text;
  v_catalyst_version text;
  v_config_sha text;
  v_scientific_fingerprint text;
  v_not_before timestamptz;
  v_activated integer := 0;
begin
  for v_spec in
    select s.*
    from public.alpha_hunter_profitability_test_specs_v01 s
    where not exists (
      select 1
      from public.alpha_hunter_profitability_test_activations_v01 a
      where a.spec_id=s.spec_id
    )
    order by s.preregistered_at_utc
  loop
    v_parent := null;
    v_not_before := v_spec.preregistered_at_utc;

    if to_regclass(
      'public.alpha_hunter_profitability_cadence_contract_v01'
    ) is not null then
      select greatest(
        v_spec.preregistered_at_utc,
        c.baseline_not_before_utc
      )
      into v_not_before
      from public.alpha_hunter_profitability_cadence_contract_v01 c
      where c.spec_id=v_spec.spec_id;

      v_not_before := coalesce(
        v_not_before,
        v_spec.preregistered_at_utc
      );
    end if;

    select p.* into v_parent
    from public.alpha_hunter_snapshots p
    where p.collected_at_utc>=v_not_before
      and (
        (
          v_spec.frozen_scientific_fingerprint_sha256 is not null
          and p.payload->'validation_identity'
            ->>'scientific_fingerprint_sha256'
              =v_spec.frozen_scientific_fingerprint_sha256
        )
        or
        (
          v_spec.frozen_scientific_fingerprint_sha256 is null
          and p.payload->'validation_identity'->>'git_commit'
            =v_spec.frozen_git_commit
        )
      )
      and p.payload->'validation_identity'->>'run_source'
        =v_spec.required_run_source
      and coalesce(
        (p.payload->'multi_strategy_summary'
          ->>'configured_strategy_count')::integer,
        0
      )=v_spec.required_strategy_count
      and coalesce(
        (p.payload->'multi_strategy_summary'
          ->>'total_evaluations')::integer,
        0
      )>0
      and coalesce(
        p.payload->'previous_snapshot_context'->>'source',
        'NONE'
      )<>'NONE'
      and coalesce(
        p.payload->'previous_snapshot_context'->>'run_source',
        ''
      )=v_spec.required_run_source
      and coalesce(
        p.payload->'catalyst_summary'->>'version',
        ''
      )='0.2'
    order by p.collected_at_utc
    limit 1;

    if v_parent.run_id is null then
      continue;
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
    into
      v_valid_symbols,
      v_strategy_rows,
      v_micro_rows,
      v_closed_rows
    from public.alpha_hunter_symbol_snapshots c
    where c.run_id=v_parent.run_id;

    if v_valid_symbols=0
       or v_strategy_rows<>v_valid_symbols
       or v_micro_rows<>v_valid_symbols
       or v_closed_rows<>v_valid_symbols
    then
      continue;
    end if;

    v_previous_source := coalesce(
      v_parent.payload->'previous_snapshot_context'->>'source',
      'NONE'
    );
    v_previous_run_source := coalesce(
      v_parent.payload->'previous_snapshot_context'->>'run_source',
      ''
    );
    v_catalyst_version := coalesce(
      v_parent.payload->'catalyst_summary'->>'version',
      ''
    );
    v_config_sha := coalesce(
      v_parent.payload->'validation_identity'->>'config_sha256',
      ''
    );
    v_scientific_fingerprint := nullif(
      v_parent.payload->'validation_identity'
        ->>'scientific_fingerprint_sha256',
      ''
    );

    if v_config_sha='' then
      continue;
    end if;

    if v_spec.frozen_scientific_fingerprint_sha256 is not null
       and v_scientific_fingerprint is distinct from
         v_spec.frozen_scientific_fingerprint_sha256
    then
      continue;
    end if;

    insert into public.alpha_hunter_profitability_test_activations_v01(
      spec_id,baseline_run_id,started_at_utc,baseline_config_sha256,
      baseline_git_commit,baseline_scientific_fingerprint_sha256,
      baseline_previous_snapshot_source,
      baseline_catalyst_version,baseline_symbol_rows,baseline_strategy_rows,
      baseline_microstructure_rows,baseline_closed_candle_rows,
      activation_checks
    ) values (
      v_spec.spec_id,v_parent.run_id,v_parent.collected_at_utc,v_config_sha,
      v_spec.frozen_git_commit,v_scientific_fingerprint,
      v_previous_source,v_catalyst_version,
      v_valid_symbols,v_strategy_rows,v_micro_rows,v_closed_rows,
      jsonb_build_object(
        'prospective_boundary_ok',
          v_parent.collected_at_utc>=v_spec.preregistered_at_utc,
        'baseline_not_before_utc',v_not_before,
        'baseline_not_before_ok',v_parent.collected_at_utc>=v_not_before,
        'required_run_source',v_spec.required_run_source,
        'run_source_ok',
          v_parent.payload->'validation_identity'->>'run_source'
            =v_spec.required_run_source,
        'scientific_fingerprint_mode',
          v_spec.frozen_scientific_fingerprint_sha256 is not null,
        'scientific_fingerprint_ok',
          case
            when v_spec.frozen_scientific_fingerprint_sha256 is null
              then true
            else v_scientific_fingerprint
              =v_spec.frozen_scientific_fingerprint_sha256
          end,
        'previous_run_source_ok',
          v_previous_run_source=v_spec.required_run_source,
        'strategy_count_ok',true,
        'previous_context_ok',true,
        'catalyst_v02_ok',true,
        'strategy_rows_complete',true,
        'microstructure_rows_complete',true,
        'closed_candle_rows_complete',true
      )
    )
    on conflict(spec_id) do nothing;

    if found then
      v_activated := v_activated+1;
    end if;
  end loop;

  return jsonb_build_object(
    'protocol_version','sealed-profitability-v0.3-scientific-fingerprint',
    'activated_specs',v_activated,
    'run_source_isolation',true,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_try_activate_profitability_test_v01()
  from public,anon,authenticated,service_role;


create or replace view public.alpha_hunter_strategy_paper_economics_v01
with (security_invoker=true,security_barrier=true)
as
with active_model as (
  select m.*
  from public.alpha_hunter_execution_cost_model_versions m
  where upper(m.status)='ACTIVE'
    and m.validated_at_utc is not null
    and m.activated_at_utc is not null
  order by m.activated_at_utc desc
  limit 1
),
cost_floor as (
  select f.*
  from public.alpha_hunter_execution_cost_floor_status_v01 f
  where f.cost_scope='ALL'
  limit 1
),
base as (
  select
    s.spec_id,
    a.started_at_utc,
    o.episode_id,
    o.symbol,
    o.strategy_id,
    o.strategy_engine_version,
    o.direction,
    o.first_observed_at_utc,
    o.first_candidate_at_utc,
    o.first_candidate_action,
    o.fill_price,
    o.first_candidate_stop_price as stop_price,
    o.first_candidate_target_price as target_price,
    o.remaining_r_at_candidate,
    o.path_outcome_class,
    o.direction_adjusted_endpoint_return_pct,
    o.path_measurement_quality,
    abs(o.fill_price-o.first_candidate_stop_price)
      /nullif(o.fill_price,0)*100.0 as risk_pct,
    cf.observable_taker_round_trip_floor_p90_bps as floor_cost_bps,
    cf.cost_model_validated as floor_cost_model_validated,
    cf.realistic_net_r_claim_permitted as floor_realistic_net_claim_permitted,
    am.cost_model_id,
    am.status as cost_model_status,
    am.taker_fee_bps,
    am.entry_slippage_bps,
    am.exit_slippage_bps
  from public.alpha_hunter_profitability_test_specs_v01 s
  join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
  join public.alpha_hunter_strategy_forward_outcomes_v01 o
    on o.first_observed_at_utc>=a.started_at_utc
   and o.horizon_hours=s.evaluation_horizon_hours
  join public.alpha_hunter_strategy_episodes_v01 ep
    on ep.episode_id=o.episode_id
  left join cost_floor cf on true
  left join active_model am on true
  where o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    and o.path_measurement_quality='COMPLETE_ENOUGH'
    and o.ordering_ambiguous=false
    and o.fill_price is not null
    and o.first_candidate_stop_price is not null
    and exists (
      select 1
      from public.alpha_hunter_strategy_observations_v01 fo
      join public.alpha_hunter_snapshots fp
        on fp.run_id=fo.run_id
      where fo.observation_id=ep.first_observation_id
        and fp.payload->'validation_identity'->>'run_source'
          =s.required_run_source
        and (
          (
            s.frozen_scientific_fingerprint_sha256 is not null
            and fp.payload->'validation_identity'
              ->>'scientific_fingerprint_sha256'
                =s.frozen_scientific_fingerprint_sha256
          )
          or
          (
            s.frozen_scientific_fingerprint_sha256 is null
            and fp.payload->'validation_identity'->>'git_commit'
              =a.baseline_git_commit
            and fp.payload->'validation_identity'->>'config_sha256'
              =a.baseline_config_sha256
          )
        )
    )
    and exists (
      select 1
      from public.alpha_hunter_strategy_observations_v01 co
      join public.alpha_hunter_snapshots cp
        on cp.run_id=co.run_id
      where co.strategy_instance_id=o.episode_id
        and co.status='SHADOW_CANDIDATE'
        and co.observed_at_utc=o.first_candidate_at_utc
        and cp.payload->'validation_identity'->>'run_source'
          =s.required_run_source
        and (
          (
            s.frozen_scientific_fingerprint_sha256 is not null
            and cp.payload->'validation_identity'
              ->>'scientific_fingerprint_sha256'
                =s.frozen_scientific_fingerprint_sha256
          )
          or
          (
            s.frozen_scientific_fingerprint_sha256 is null
            and cp.payload->'validation_identity'->>'git_commit'
              =a.baseline_git_commit
            and cp.payload->'validation_identity'->>'config_sha256'
              =a.baseline_config_sha256
          )
        )
    )
),
gross as (
  select
    b.*,
    case
      when b.path_outcome_class='TARGET_FIRST'
        then b.remaining_r_at_candidate
      when b.path_outcome_class='STOP_FIRST'
        then -1.0
      when b.path_outcome_class='OPEN_AT_HORIZON'
        then b.direction_adjusted_endpoint_return_pct/nullif(b.risk_pct,0)
      else null
    end as gross_r_pre_cost
  from base b
)
select
  g.*,
  (g.floor_cost_bps/100.0)/nullif(g.risk_pct,0)
    as observed_floor_cost_r,
  g.gross_r_pre_cost
    - (g.floor_cost_bps/100.0)/nullif(g.risk_pct,0)
    as floor_adjusted_r,
  case
    when g.cost_model_status='ACTIVE'
     and g.taker_fee_bps is not null
     and g.entry_slippage_bps is not null
     and g.exit_slippage_bps is not null
    then (
      (
        2.0*g.taker_fee_bps
        + g.entry_slippage_bps
        + g.exit_slippage_bps
      )/100.0
    )/nullif(g.risk_pct,0)
    else null
  end as modeled_cost_r,
  case
    when g.cost_model_status='ACTIVE'
     and g.floor_realistic_net_claim_permitted is true
     and g.taker_fee_bps is not null
     and g.entry_slippage_bps is not null
     and g.exit_slippage_bps is not null
    then g.gross_r_pre_cost - (
      (
        2.0*g.taker_fee_bps
        + g.entry_slippage_bps
        + g.exit_slippage_bps
      )/100.0
    )/nullif(g.risk_pct,0)
    else null
  end as modeled_net_r,
  case
    when g.cost_model_status='ACTIVE'
     and g.floor_realistic_net_claim_permitted is true
      then 'VALIDATED_COST_MODEL_AVAILABLE'
    else 'NO_VALIDATED_REALISTIC_NET_MODEL'
  end as net_economic_status,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  true as source_isolated
from gross g
where g.gross_r_pre_cost is not null
  and g.risk_pct>0;

revoke all on public.alpha_hunter_strategy_paper_economics_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_strategy_paper_economics_v01
  to service_role;


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
    a.baseline_scientific_fingerprint_sha256,
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
        (
          sa.frozen_scientific_fingerprint_sha256 is not null
          and coalesce(
            p.payload->'validation_identity'
              ->>'scientific_fingerprint_sha256',
            ''
          ) <> sa.frozen_scientific_fingerprint_sha256
        )
        or
        (
          sa.frozen_scientific_fingerprint_sha256 is null
          and (
            coalesce(p.payload->'validation_identity'->>'git_commit','')
              <>sa.baseline_git_commit
            or coalesce(
              p.payload->'validation_identity'->>'config_sha256',
              ''
            ) <> sa.baseline_config_sha256
          )
        )
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
        - sa.confidence_z*e.sd_floor_adjusted_r/sqrt(e.completed_paper_trades)
    else null
  end as floor_adjusted_r_lower_95,
  e.floor_profit_factor,
  coalesce(e.modeled_net_trade_count,0) as modeled_net_trade_count,
  e.avg_modeled_net_r,
  case
    when coalesce(e.modeled_net_trade_count,0)>=2
      then e.avg_modeled_net_r
        - sa.confidence_z*e.sd_modeled_net_r/sqrt(e.modeled_net_trade_count)
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
    coalesce(e.completed_paper_trades,0)
      >=sa.minimum_completed_paper_trades
    and e.avg_floor_adjusted_r is not null
    and e.avg_floor_adjusted_r
      - sa.confidence_z*e.sd_floor_adjusted_r
        /sqrt(e.completed_paper_trades) > 0
    and coalesce(e.floor_profit_factor,0)>1.0
  ) as conservative_floor_edge_gate_met,
  (
    coalesce(e.modeled_net_trade_count,0)
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
    when sa.started_at_utc is null then 'ARMED_WAITING_FOR_CLEAN_BASELINE'
    when coalesce(d.drift_scans,0)>0 then 'INVALIDATED_BY_BUILD_OR_CONFIG_DRIFT'
    when extract(epoch from (clock_timestamp()-sa.started_at_utc))/86400.0
      <sa.minimum_test_days then 'RUNNING_MINIMUM_DURATION_NOT_MET'
    when coalesce(e.completed_paper_trades,0)
      <sa.minimum_completed_paper_trades then 'RUNNING_SAMPLE_NOT_MET'
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
  true as run_source_isolated,
  (sa.frozen_scientific_fingerprint_sha256 is not null)
    as scientific_fingerprint_enabled,
  sa.frozen_scientific_fingerprint_sha256,
  sa.baseline_scientific_fingerprint_sha256
from spec_activation sa
left join drift d on d.spec_id=sa.spec_id
left join econ e on e.spec_id=sa.spec_id
left join cost_status cs on true;

revoke all on public.alpha_hunter_profitability_validation_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_validation_status_v01
  to service_role;
