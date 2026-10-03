-- Alpha Hunter paper-production confidence-band gate v0.1
--
-- User production order:
--   Create the first PAPER trade only when a fresh Alpha Hunter signal has
--   confidence_estimate_pct in [65,70] and reward_risk >= 5.
--
-- Scientific wording:
--   confidence_estimate_pct is a model confidence field, NOT a validated
--   empirical win-rate claim.
--
-- Safety:
--   PAPER ONLY; no exchange write path; normalized virtual risk = 1R;
--   trade_permission=false; live_order_authority=false.

create table if not exists private.alpha_hunter_paper_production_policy_v01 (
  policy_id text primary key,
  status text not null check(status in ('ACTIVE','PAUSED','RETIRED')),
  confidence_min_pct double precision not null,
  confidence_max_pct double precision not null,
  minimum_reward_risk double precision not null,
  max_active_paper_trades integer not null default 1,
  normalized_virtual_risk_r double precision not null default 1.0,
  evidence jsonb not null default '{}'::jsonb,
  paper_only boolean not null default true check(paper_only=true),
  live_order_authority boolean not null default false check(live_order_authority=false),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  check(confidence_min_pct>=0 and confidence_max_pct<=100),
  check(confidence_min_pct<=confidence_max_pct),
  check(minimum_reward_risk>0),
  check(max_active_paper_trades>=1),
  check(normalized_virtual_risk_r>0)
);

create table if not exists private.alpha_hunter_paper_orders_v01 (
  paper_order_id text primary key,
  policy_id text not null references private.alpha_hunter_paper_production_policy_v01(policy_id),
  signal_id text not null unique,
  run_id text not null,
  symbol text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  signal_state text,
  detected_at_utc timestamptz not null,
  paper_filled_at_utc timestamptz not null,
  paper_fill_price double precision not null check(paper_fill_price>0),
  stop_price double precision not null check(stop_price>0),
  target_price double precision not null check(target_price>0),
  confidence_estimate_pct double precision not null,
  reward_risk double precision not null,
  normalized_virtual_risk_r double precision not null default 1.0,
  state text not null default 'FILLED_PAPER'
    check(state in ('FILLED_PAPER','CLOSED_WIN','CLOSED_LOSS','CLOSED_OTHER','CANCELLED')),
  evidence jsonb not null default '{}'::jsonb,
  paper_only boolean not null default true check(paper_only=true),
  live_exchange_order_sent boolean not null default false check(live_exchange_order_sent=false),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_paper_orders_v01_state_time
  on private.alpha_hunter_paper_orders_v01(state,paper_filled_at_utc desc);

insert into private.alpha_hunter_paper_production_policy_v01(
  policy_id,status,confidence_min_pct,confidence_max_pct,minimum_reward_risk,
  max_active_paper_trades,normalized_virtual_risk_r,evidence,
  paper_only,live_order_authority,trade_permission
) values (
  'PAPER-PROD-65-70-RR5-V01',
  'ACTIVE',
  65.0,
  70.0,
  5.0,
  1,
  1.0,
  jsonb_build_object(
    'user_order','FIRST_PAPER_TRADE_65_TO_70_BAND',
    'confidence_semantics','ALPHA_HUNTER_SIGNAL_CONFIDENCE_NOT_VALIDATED_WIN_RATE',
    'empirical_win_rate_claim_permitted',false,
    'minimum_reward_risk_source','SEALED_PROFITABILITY_MINIMUM_RR_5',
    'fill_model','IMMEDIATE_PAPER_FILL_AT_SIGNAL_ENTRY',
    'virtual_risk_model','NORMALIZED_1R',
    'bitget_order_permitted',false,
    'live_money_permitted',false
  ),
  true,false,false
)
on conflict(policy_id) do update
set status='ACTIVE',
    confidence_min_pct=excluded.confidence_min_pct,
    confidence_max_pct=excluded.confidence_max_pct,
    minimum_reward_risk=excluded.minimum_reward_risk,
    max_active_paper_trades=excluded.max_active_paper_trades,
    normalized_virtual_risk_r=excluded.normalized_virtual_risk_r,
    evidence=excluded.evidence,
    updated_at=clock_timestamp();

create or replace function private.alpha_hunter_create_paper_order_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  p private.alpha_hunter_paper_production_policy_v01%rowtype;
  v_active_count integer;
  v_order_id text;
begin
  select * into p
  from private.alpha_hunter_paper_production_policy_v01
  where status='ACTIVE'
  order by updated_at desc
  limit 1;

  if p.policy_id is null then
    return new;
  end if;

  if new.confidence_estimate_pct is null
     or new.reward_risk is null
     or new.entry_price is null
     or new.stop_loss is null
     or new.take_profit is null
     or new.direction not in ('LONG','SHORT')
  then
    return new;
  end if;

  if new.confidence_estimate_pct<p.confidence_min_pct
     or new.confidence_estimate_pct>p.confidence_max_pct
     or new.reward_risk<p.minimum_reward_risk
  then
    return new;
  end if;

  if new.entry_price<=0 or new.stop_loss<=0 or new.take_profit<=0 then
    return new;
  end if;

  if new.direction='LONG'
     and not (new.stop_loss<new.entry_price and new.entry_price<new.take_profit)
  then
    return new;
  end if;

  if new.direction='SHORT'
     and not (new.take_profit<new.entry_price and new.entry_price<new.stop_loss)
  then
    return new;
  end if;

  select count(*) into v_active_count
  from private.alpha_hunter_paper_orders_v01
  where state='FILLED_PAPER';

  if v_active_count>=p.max_active_paper_trades then
    return new;
  end if;

  v_order_id:='paper-'||md5(p.policy_id||'|'||new.signal_id);

  insert into private.alpha_hunter_paper_orders_v01(
    paper_order_id,policy_id,signal_id,run_id,symbol,direction,signal_state,
    detected_at_utc,paper_filled_at_utc,paper_fill_price,stop_price,target_price,
    confidence_estimate_pct,reward_risk,normalized_virtual_risk_r,state,evidence,
    paper_only,live_exchange_order_sent,trade_permission
  ) values (
    v_order_id,p.policy_id,new.signal_id,new.run_id,new.symbol,new.direction,new.state,
    new.detected_at_utc,greatest(clock_timestamp(),new.detected_at_utc),
    new.entry_price,new.stop_loss,new.take_profit,new.confidence_estimate_pct,
    new.reward_risk,p.normalized_virtual_risk_r,'FILLED_PAPER',
    jsonb_build_object(
      'source','ALPHA_HUNTER_SIGNAL_TRIGGER',
      'signal_trade_permission',new.trade_permission,
      'confidence_semantics','MODEL_CONFIDENCE_NOT_VALIDATED_WIN_RATE',
      'production_order','PAPER_ONLY_65_TO_70_BAND',
      'bitget_order_sent',false,
      'live_money_permitted',false
    ),
    true,false,false
  )
  on conflict(signal_id) do nothing;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_create_paper_order_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_create_paper_order_v01 on public.alpha_hunter_signals;
create trigger trg_ah_create_paper_order_v01
after insert on public.alpha_hunter_signals
for each row execute function private.alpha_hunter_create_paper_order_v01();

-- Do not backfill historical signals. Only signals inserted after deployment
-- may create a paper order, eliminating hindsight selection.
