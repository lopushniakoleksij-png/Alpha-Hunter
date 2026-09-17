-- Alpha Hunter public venue fee evidence v0.1
-- Forward-only evidence enrichment from the already-fetched Bitget V3 instrument payload.
-- This does NOT activate/validate a cost model and does NOT permit realistic_net_r.

alter table public.alpha_hunter_universe_hourly
  add column if not exists public_maker_fee_bps double precision,
  add column if not exists public_taker_fee_bps double precision,
  add column if not exists fee_rate_source text;

create or replace function private.alpha_hunter_bind_public_fee_evidence()
returns trigger
language plpgsql
security definer
set search_path=''
as $$
declare
  v_maker_fee_bps double precision;
  v_taker_fee_bps double precision;
  v_fee_rate_source text;
begin
  -- An activated validated model, if one exists in the future, remains authoritative.
  if new.cost_model_id is not null
     or new.maker_fee_bps is not null
     or new.taker_fee_bps is not null then
    return new;
  end if;

  select
    u.public_maker_fee_bps,
    u.public_taker_fee_bps,
    u.fee_rate_source
  into
    v_maker_fee_bps,
    v_taker_fee_bps,
    v_fee_rate_source
  from public.alpha_hunter_universe_hourly u
  where u.symbol=upper(new.symbol)
    and u.selection_run_id=new.source_run_id
    and u.hour_bucket_utc=date_trunc('hour',new.captured_at_utc)
    and u.public_maker_fee_bps is not null
    and u.public_taker_fee_bps is not null
    and u.fee_rate_source='BITGET_V3_INSTRUMENT_PUBLIC'
    and u.trade_permission=false
  order by u.observed_at_utc desc
  limit 1;

  if v_maker_fee_bps is null or v_taker_fee_bps is null then
    return new;
  end if;

  new.maker_fee_bps := v_maker_fee_bps;
  new.taker_fee_bps := v_taker_fee_bps;
  new.evidence := coalesce(new.evidence,'{}'::jsonb) || jsonb_build_object(
    'venue_base_fee_observed',true,
    'venue_base_fee_source',v_fee_rate_source,
    'venue_base_maker_fee_bps',v_maker_fee_bps,
    'venue_base_taker_fee_bps',v_taker_fee_bps,
    'account_specific_fee_verified',false,
    'fee_evidence_is_not_cost_model',true,
    'fee_evidence_does_not_permit_realistic_net_r',true
  );

  -- Deliberately do not set cost_model_id/status, slippage, estimated cost R,
  -- realistic_net_r, or any execution authority here.
  return new;
end;
$$;

revoke all on function private.alpha_hunter_bind_public_fee_evidence() from public,anon,authenticated;

drop trigger if exists alpha_hunter_execution_cost_public_fee_evidence on public.alpha_hunter_execution_cost_evidence;
create trigger alpha_hunter_execution_cost_public_fee_evidence
before insert on public.alpha_hunter_execution_cost_evidence
for each row execute function private.alpha_hunter_bind_public_fee_evidence();
