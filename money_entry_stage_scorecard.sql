-- Alpha Hunter Money Entry stage -> forward scorecard linkage v0.1
-- Future scorecard candidates link the exact immutable stage snapshot when one exists.

alter table public.alpha_hunter_big_mover_money_scorecard_candidates
  add column if not exists money_entry_stage_snapshot_id text
  references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id);

create or replace function private.alpha_hunter_seed_big_mover_money_scorecard()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_candidates integer:=0;
  v_outcomes integer:=0;
begin
  with src as (
    select
      b.*,
      ms.stage_snapshot_id,
      ms.stage_status exact_stage_status,
      ms.blockers exact_stage_blockers,
      ms.next_stage_blockers exact_next_stage_blockers,
      case
        when b.direction='LONG'
          and b.candidate_entry is not null
          and b.stop_price is not null
          and b.target_price is not null
          and b.stop_price<b.candidate_entry
          and b.target_price>b.candidate_entry then true
        when b.direction='SHORT'
          and b.candidate_entry is not null
          and b.stop_price is not null
          and b.target_price is not null
          and b.stop_price>b.candidate_entry
          and b.target_price<b.candidate_entry then true
        else false
      end geometry_ok
    from public.alpha_hunter_big_mover_money_entry_shadow b
    left join public.alpha_hunter_money_entry_stage_snapshots ms
      on ms.source_bridge_id=b.bridge_id
    where b.research_status='SHADOW_QUEUE'
      and b.lifecycle in ('PRE_MOVER','IGNITION')
  ), ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_candidates(
      scorecard_id,source_bridge_id,run_id,candidate_at_utc,symbol,direction,
      candidate_entry,stop_price,target_price,geometry_valid,risk_distance_abs,
      risk_distance_pct,initial_remaining_r,similarity_score,feature_coverage,
      lifecycle,research_status,bridge_status,raw_change_24h_pct,
      direction_normalized_move_pct,scanner_direction,direction_1h,direction_4h,
      direction_12h,direction_1d,liquidity_state,opportunity_timing,
      candidate_quality_status,bridge_blockers,frozen_evidence,
      stage_snapshot_status,t0_snapshot_available,t1_snapshot_available,
      t2_snapshot_available,money_entry_stage_snapshot_id,model_version,
      shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-v0.1|'||s.bridge_id),
      s.bridge_id,s.run_id,s.captured_at_utc,s.symbol,s.direction,
      s.candidate_entry,s.stop_price,s.target_price,s.geometry_ok,
      case when s.geometry_ok then abs(s.candidate_entry-s.stop_price) end,
      case
        when s.geometry_ok and s.candidate_entry<>0
          then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0
      end,
      case
        when s.geometry_ok and abs(s.candidate_entry-s.stop_price)>0
          then abs(s.target_price-s.candidate_entry)/abs(s.candidate_entry-s.stop_price)
      end,
      s.similarity_score,s.feature_coverage,s.lifecycle,s.research_status,
      s.bridge_status,s.raw_change_24h_pct,s.direction_normalized_move_pct,
      s.scanner_direction,s.direction_1h,s.direction_4h,s.direction_12h,
      s.direction_1d,s.liquidity_state,s.opportunity_timing,
      s.candidate_quality_status,s.blockers,
      coalesce(s.evidence,'{}'::jsonb)||jsonb_build_object(
        'frozen_from_bridge_at_utc',clock_timestamp(),
        'source_bridge_model_version',s.model_version,
        'geometry_valid_for_signature_direction',s.geometry_ok,
        'money_entry_stage_snapshot_id',s.stage_snapshot_id,
        'money_entry_stage_blockers',coalesce(s.exact_stage_blockers,'[]'::jsonb),
        'money_entry_next_stage_blockers',coalesce(s.exact_next_stage_blockers,'[]'::jsonb),
        'exact_stage_claim_permitted',
          s.exact_stage_status in (
            'T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'
          )
      ),
      coalesce(s.exact_stage_status,'EXACT_T0_T1_T2_NOT_CAPTURED'),
      s.exact_stage_status='T0_CONTROLLED_ENTRY',
      s.exact_stage_status='T1_ACCEPTANCE_CONFIRMED',
      s.exact_stage_status='T2_EXPANSION_CONFIRMED',
      s.stage_snapshot_id,
      'big-mover-money-scorecard-v0.2-stage-linked',
      true,false
    from src s
    on conflict(source_bridge_id) do nothing
    returning 1
  )
  select count(*) into v_candidates from ins;

  with ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_outcomes(
      outcome_id,scorecard_id,horizon_hours,horizon_due_at_utc,
      evaluation_status,realistic_net_r_status,confirmation_tax_status,
      t0_path_result,t1_path_result,t2_path_result,stage_outcome_status,
      evidence,shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-outcome-v0.1|'||c.scorecard_id||'|'||h.h::text),
      c.scorecard_id,
      h.h,
      c.candidate_at_utc+make_interval(hours=>h.h),
      'PENDING',
      'UNVERIFIED_EXECUTION_COST_MODEL',
      'NOT_LINKED',
      'NOT_EVALUABLE',
      'NOT_EVALUABLE',
      'NOT_EVALUABLE',
      case
        when c.money_entry_stage_snapshot_id is not null
          then 'EXACT_STAGE_SNAPSHOT_LINKED_PENDING_OUTCOME'
        else 'EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE'
      end,
      jsonb_build_object(
        'measurement_source','BITGET_PUBLIC_V3_3M_CANDLES',
        'money_entry_stage_snapshot_id',c.money_entry_stage_snapshot_id,
        'stage_snapshot_status',c.stage_snapshot_status,
        'exact_stage_claim_permitted',c.money_entry_stage_snapshot_id is not null
      ),
      true,false
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    cross join(values(1),(4),(12),(24)) h(h)
    on conflict(scorecard_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_outcomes from ins;

  return jsonb_build_object(
    'mode','BIG_MOVER_FORWARD_MONEY_SCORECARD_SEED',
    'candidates_seeded',v_candidates,
    'outcomes_seeded',v_outcomes,
    'stage_linking','EXACT_IMMUTABLE_SNAPSHOT_WHEN_AVAILABLE',
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_seed_big_mover_money_scorecard()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_seed_big_mover_money_scorecard()
  to service_role;
