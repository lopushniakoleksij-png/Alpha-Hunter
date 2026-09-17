begin;

-- PR #52 already established the canonical forward-only BEFORE INSERT trigger
-- as the public fee evidence writer. Remove the later redundant function-level
-- fee binding so one authoritative layer owns fee enrichment.
-- This migration does not rewrite historical evidence.
do $patch$
declare
  v_def text;
  v_trigger_def text;
  v_trigger_fn_def text;
  v_new_base text := $new$with base as (
    select s.*,
      coalesce(sf.source_payload,'{}'::jsonb) as source_payload,
      uf.public_maker_fee_bps as observed_public_maker_fee_bps,
      uf.public_taker_fee_bps as observed_public_taker_fee_bps,
      uf.fee_rate_source as observed_fee_rate_source
    from public.alpha_hunter_money_entry_stage_snapshots s
    left join lateral (
      select f.source_payload from public.alpha_hunter_signal_features f
      where (s.source_signal_id is not null and f.signal_id=s.source_signal_id)
         or (s.source_signal_id is null and f.run_id=s.source_run_id and f.symbol=s.symbol)
      order by case when s.source_signal_id is not null and f.signal_id=s.source_signal_id then 0 else 1 end,
               f.captured_at_utc desc
      limit 1
    ) sf on true
    left join lateral (
      select u.public_maker_fee_bps,u.public_taker_fee_bps,u.fee_rate_source
      from public.alpha_hunter_universe_hourly u
      where u.selection_run_id=s.source_run_id
        and u.symbol=s.symbol
        and u.observed_at_utc<=s.source_captured_at_utc
        and u.trade_permission=false
      order by u.observed_at_utc desc
      limit 1
    ) uf on true
    where s.control_run_id=p_control_run_id
  ), normalized as ($new$;
  v_old_base text := $old$with base as (
    select s.*,
      coalesce(sf.source_payload,'{}'::jsonb) as source_payload
    from public.alpha_hunter_money_entry_stage_snapshots s
    left join lateral (
      select f.source_payload from public.alpha_hunter_signal_features f
      where (s.source_signal_id is not null and f.signal_id=s.source_signal_id)
         or (s.source_signal_id is null and f.run_id=s.source_run_id and f.symbol=s.symbol)
      order by case when s.source_signal_id is not null and f.signal_id=s.source_signal_id then 0 else 1 end,
               f.captured_at_utc desc
      limit 1
    ) sf on true
    where s.control_run_id=p_control_run_id
  ), normalized as ($old$;
  v_new_fee_values text := $new$n.quote_volume,n.liquidity_state,
      v_cost_model_id,v_cost_model_status,
      coalesce(v_maker_fee_bps,n.observed_public_maker_fee_bps),
      coalesce(v_taker_fee_bps,n.observed_public_taker_fee_bps),
      v_entry_slippage_bps,v_exit_slippage_bps,
      case when v_cost_model_id is not null then 2.0*v_taker_fee_bps+v_entry_slippage_bps+v_exit_slippage_bps end,$new$;
  v_old_fee_values text := $old$n.quote_volume,n.liquidity_state,
      v_cost_model_id,v_cost_model_status,v_maker_fee_bps,v_taker_fee_bps,v_entry_slippage_bps,v_exit_slippage_bps,
      case when v_cost_model_id is not null then 2.0*v_taker_fee_bps+v_entry_slippage_bps+v_exit_slippage_bps end,$old$;
  v_new_evidence text := $new$'fee_model_verified',v_cost_model_id is not null,
        'public_fee_evidence_observed',n.observed_public_maker_fee_bps is not null and n.observed_public_taker_fee_bps is not null,
        'fee_value_source',case
          when v_cost_model_id is not null then 'ACTIVE_VALIDATED_COST_MODEL'
          when n.observed_public_maker_fee_bps is not null and n.observed_public_taker_fee_bps is not null then coalesce(n.observed_fee_rate_source,'PUBLIC_FEE_EVIDENCE')
          else 'UNAVAILABLE'
        end,
        'public_fee_evidence_used_as_cost_model',false,
        'slippage_model_verified',v_cost_model_id is not null and v_entry_slippage_bps is not null and v_exit_slippage_bps is not null,
        'funding_included_in_realistic_net_r',false,
        'realistic_net_r_claim_permitted',false,
        'no_fee_or_slippage_values_invented',true$new$;
  v_old_evidence text := $old$'fee_model_verified',v_cost_model_id is not null,
        'funding_included_in_realistic_net_r',false,
        'realistic_net_r_claim_permitted',false,
        'no_fee_or_slippage_values_invented',true$old$;
begin
  select pg_get_functiondef(p.oid)
    into v_def
  from pg_proc p
  join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='private'
    and p.proname='alpha_hunter_capture_execution_cost_evidence'
    and pg_get_function_identity_arguments(p.oid)='p_control_run_id text';

  select pg_get_triggerdef(t.oid)
    into v_trigger_def
  from pg_trigger t
  join pg_class c on c.oid=t.tgrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='alpha_hunter_execution_cost_evidence'
    and t.tgname='alpha_hunter_execution_cost_public_fee_evidence'
    and not t.tgisinternal;

  select pg_get_functiondef(p.oid)
    into v_trigger_fn_def
  from pg_proc p
  join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='private'
    and p.proname='alpha_hunter_bind_public_fee_evidence'
    and p.prokind='f';

  if v_def is null then
    raise exception 'expected execution cost evidence function not found';
  end if;
  if v_trigger_def is null or position('alpha_hunter_bind_public_fee_evidence' in v_trigger_def)=0 then
    raise exception 'canonical public fee trigger missing; refusing single-writer consolidation';
  end if;
  if v_trigger_fn_def is null
     or position('u.selection_run_id=new.source_run_id' in v_trigger_fn_def)=0
     or position($needle$u.hour_bucket_utc=date_trunc('hour',new.captured_at_utc)$needle$ in v_trigger_fn_def)=0
     or position($needle$u.fee_rate_source='BITGET_V3_INSTRUMENT_PUBLIC'$needle$ in v_trigger_fn_def)=0
     or position($needle$'fee_evidence_is_not_cost_model',true$needle$ in v_trigger_fn_def)=0
     or position($needle$'fee_evidence_does_not_permit_realistic_net_r',true$needle$ in v_trigger_fn_def)=0 then
    raise exception 'canonical public fee trigger contract drifted; refusing single-writer consolidation';
  end if;
  if position(v_new_base in v_def)=0
     or position(v_new_fee_values in v_def)=0
     or position(v_new_evidence in v_def)=0 then
    raise exception 'redundant function-level fee binding contract drifted; refusing consolidation';
  end if;
  if position('WITHHELD_NO_ACTIVE_VALIDATED_COST_MODEL' in v_def)=0 then
    raise exception 'net-R fail-closed contract drifted; refusing consolidation';
  end if;

  v_def := replace(v_def,v_new_base,v_old_base);
  v_def := replace(v_def,v_new_fee_values,v_old_fee_values);
  v_def := replace(v_def,v_new_evidence,v_old_evidence);
  execute v_def;
end;
$patch$;

commit;
