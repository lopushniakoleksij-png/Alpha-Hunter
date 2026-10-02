-- Alpha Hunter forward profit-management shadow monitor v0.1
--
-- Purpose:
--   Persist the preregistered profit-management challengers prospectively on
--   every FUTURE canonical open-position snapshot.
--
-- Forward-only contract:
--   * installation creates one activation timestamp;
--   * the trigger runs only for position snapshots captured at/after activation;
--   * there is no INSERT...SELECT historical backfill path;
--   * existing historical trades remain retrospective evidence only.
--
-- Episode continuity:
--   * continuation requires the same symbol/direction in the immediately
--     previous canonical account snapshot from the same account source;
--   * average entry must remain materially unchanged;
--   * otherwise a new shadow episode is started rather than guessed.
--
-- Safety:
--   * shadow evidence only;
--   * no exchange calls;
--   * no live stop/TP/order/leverage changes;
--   * trade_permission=false and order_path=NONE always.

create table if not exists public.alpha_hunter_profit_management_forward_config_v01 (
  config_id text primary key
    check (config_id='profit-management-forward-v0.1'),
  activated_at_utc timestamptz not null default clock_timestamp(),
  policy_count integer not null default 3 check (policy_count=3),
  model_version text not null default 'profit-management-forward-v0.1'
    check (model_version='profit-management-forward-v0.1'),
  forward_only boolean not null default true check (forward_only=true),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into public.alpha_hunter_profit_management_forward_config_v01(config_id)
values ('profit-management-forward-v0.1')
on conflict(config_id) do nothing;

alter table public.alpha_hunter_profit_management_forward_config_v01
  enable row level security;

revoke all on public.alpha_hunter_profit_management_forward_config_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profit_management_forward_config_v01
  to service_role;

drop trigger if exists trg_ah_profit_management_forward_config_append_only_v01
  on public.alpha_hunter_profit_management_forward_config_v01;
create trigger trg_ah_profit_management_forward_config_append_only_v01
before update or delete
on public.alpha_hunter_profit_management_forward_config_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create table if not exists public.alpha_hunter_profit_management_forward_v01 (
  observation_id text primary key,
  position_snapshot_id text not null
    references public.alpha_hunter_open_position_snapshots(position_snapshot_id)
    on delete restrict,
  account_snapshot_id text not null
    references public.alpha_hunter_account_state_snapshots(account_snapshot_id)
    on delete restrict,
  captured_at_utc timestamptz not null,

  episode_id text not null,
  episode_started_at_utc timestamptz not null,
  continuity_status text not null check (
    continuity_status in (
      'NEW_FORWARD_EPISODE',
      'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT',
      'ENTRY_CHANGED_RESTART',
      'FORWARD_ANCHOR_MISSING_RESTART'
    )
  ),
  previous_position_snapshot_id text,

  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  quantity double precision not null,
  average_entry double precision not null,
  mark_price double precision not null,
  episode_entry_price double precision not null,
  episode_initial_quantity double precision not null,

  policy_id text not null check (
    policy_id in (
      'BE_AFTER_3PCT',
      'LOCK_25_AFTER_5PCT',
      'LOCK_50_AFTER_5PCT'
    )
  ),
  activation_favorable_pct double precision not null,
  lock_fraction double precision not null,
  threshold_basis text not null,

  running_favorable_mark double precision not null,
  running_favorable_pct double precision not null,
  policy_active boolean not null,
  policy_activated_at_utc timestamptz,
  shadow_stop_price double precision,
  shadow_state text not null check (
    shadow_state in ('INACTIVE','ACTIVE','TRIGGERED')
  ),
  trigger_observed_on_this_snapshot boolean not null default false,
  shadow_trigger_at_utc timestamptz,
  shadow_trigger_observed_mark double precision,
  shadow_stop_at_trigger double precision,

  entry_changed_from_previous boolean not null default false,
  quantity_changed_from_previous boolean not null default false,
  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence)='object'),

  forward_only boolean not null default true check (forward_only=true),
  sampled_mark_limitation boolean not null default true
    check (sampled_mark_limitation=true),
  counterfactual_fee_claim_permitted boolean not null default false
    check (counterfactual_fee_claim_permitted=false),
  counterfactual_funding_claim_permitted boolean not null default false
    check (counterfactual_funding_claim_permitted=false),
  counterfactual_net_pnl_claim_permitted boolean not null default false
    check (counterfactual_net_pnl_claim_permitted=false),
  management_change_permitted boolean not null default false
    check (management_change_permitted=false),
  stop_change_permitted boolean not null default false
    check (stop_change_permitted=false),
  target_change_permitted boolean not null default false
    check (target_change_permitted=false),
  promotion_permitted boolean not null default false
    check (promotion_permitted=false),
  model_version text not null default 'profit-management-forward-v0.1'
    check (model_version='profit-management-forward-v0.1'),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),

  unique(position_snapshot_id,policy_id)
);

create index if not exists idx_ah_profit_management_forward_episode_v01
  on public.alpha_hunter_profit_management_forward_v01(
    episode_id,policy_id,captured_at_utc
  );

create index if not exists idx_ah_profit_management_forward_symbol_v01
  on public.alpha_hunter_profit_management_forward_v01(
    symbol,direction,captured_at_utc desc
  );

alter table public.alpha_hunter_profit_management_forward_v01
  enable row level security;

revoke all on public.alpha_hunter_profit_management_forward_v01
  from public,anon,authenticated,service_role;
grant select,insert on public.alpha_hunter_profit_management_forward_v01
  to service_role;

drop trigger if exists trg_ah_profit_management_forward_append_only_v01
  on public.alpha_hunter_profit_management_forward_v01;
create trigger trg_ah_profit_management_forward_append_only_v01
before update or delete on public.alpha_hunter_profit_management_forward_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_materialize_profit_management_forward_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $$
declare
  v_activated_at timestamptz;
  v_current_source text;
  v_prev_account_id text;
  v_prev_position_id text;
  v_prev_average_entry double precision;
  v_prev_quantity double precision;
  v_anchor_episode_id text;
  v_anchor_episode_started_at timestamptz;
  v_anchor_entry_price double precision;
  v_anchor_initial_quantity double precision;
  v_continuity_status text;
  v_entry_changed boolean := false;
  v_quantity_changed boolean := false;
  v_entry_tolerance double precision;

  v_policy record;
  v_prev_policy public.alpha_hunter_profit_management_forward_v01%rowtype;

  v_running_favorable_mark double precision;
  v_running_favorable_pct double precision;
  v_policy_active boolean;
  v_policy_activated_at timestamptz;
  v_shadow_stop double precision;
  v_shadow_state text;
  v_trigger_now boolean;
  v_trigger_at timestamptz;
  v_trigger_mark double precision;
  v_trigger_stop double precision;
  v_observation_id text;
begin
  select c.activated_at_utc
    into v_activated_at
  from public.alpha_hunter_profit_management_forward_config_v01 c
  where c.config_id='profit-management-forward-v0.1';

  if v_activated_at is null or new.captured_at_utc < v_activated_at then
    return new;
  end if;

  if new.direction not in ('LONG','SHORT')
     or new.average_entry is null
     or new.average_entry <= 0
     or new.mark_price is null
     or new.mark_price <= 0
     or new.quantity is null
     or new.quantity <= 0 then
    return new;
  end if;

  select a.source
    into v_current_source
  from public.alpha_hunter_account_state_snapshots a
  where a.account_snapshot_id=new.account_snapshot_id;

  select a.account_snapshot_id
    into v_prev_account_id
  from public.alpha_hunter_account_state_snapshots a
  where a.captured_at_utc < new.captured_at_utc
    and (
      v_current_source is null
      or a.source is not distinct from v_current_source
    )
  order by a.captured_at_utc desc,a.account_snapshot_id desc
  limit 1;

  if v_prev_account_id is not null then
    select
      p.position_snapshot_id,
      p.average_entry,
      p.quantity
    into
      v_prev_position_id,
      v_prev_average_entry,
      v_prev_quantity
    from public.alpha_hunter_open_position_snapshots p
    where p.account_snapshot_id=v_prev_account_id
      and p.symbol=new.symbol
      and p.direction=new.direction
    order by p.position_snapshot_id
    limit 1;
  end if;

  if v_prev_position_id is null then
    v_continuity_status := 'NEW_FORWARD_EPISODE';

  else
    v_entry_tolerance := greatest(
      1e-9,
      abs(new.average_entry)*1e-8,
      abs(coalesce(v_prev_average_entry,new.average_entry))*1e-8
    );

    v_entry_changed := (
      v_prev_average_entry is null
      or abs(new.average_entry-v_prev_average_entry) > v_entry_tolerance
    );

    v_quantity_changed := (
      v_prev_quantity is null
      or abs(new.quantity-v_prev_quantity)
        > greatest(
            1e-9,
            abs(new.quantity)*1e-8,
            abs(coalesce(v_prev_quantity,new.quantity))*1e-8
          )
    );

    if v_entry_changed then
      v_continuity_status := 'ENTRY_CHANGED_RESTART';
    else
      select
        f.episode_id,
        f.episode_started_at_utc,
        f.episode_entry_price,
        f.episode_initial_quantity
      into
        v_anchor_episode_id,
        v_anchor_episode_started_at,
        v_anchor_entry_price,
        v_anchor_initial_quantity
      from public.alpha_hunter_profit_management_forward_v01 f
      where f.position_snapshot_id=v_prev_position_id
      order by f.policy_id
      limit 1;

      if v_anchor_episode_id is null then
        v_continuity_status := 'FORWARD_ANCHOR_MISSING_RESTART';
      else
        v_continuity_status := 'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT';
      end if;
    end if;
  end if;

  if v_continuity_status <> 'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT' then
    v_anchor_episode_id := substr(
      encode(
        extensions.digest(
          'profit-management-forward-v0.1|episode|' || new.position_snapshot_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    );
    v_anchor_episode_started_at := new.captured_at_utc;
    v_anchor_entry_price := new.average_entry;
    v_anchor_initial_quantity := new.quantity;
  end if;

  for v_policy in
    select *
    from (
      values
        (
          'BE_AFTER_3PCT'::text,
          3.0::double precision,
          0.0::double precision,
          'EXISTING_LIFECYCLE_3PCT_MILESTONE'::text
        ),
        (
          'LOCK_25_AFTER_5PCT'::text,
          5.0::double precision,
          0.25::double precision,
          'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
        ),
        (
          'LOCK_50_AFTER_5PCT'::text,
          5.0::double precision,
          0.50::double precision,
          'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
        )
    ) as p(policy_id,activation_favorable_pct,lock_fraction,threshold_basis)
  loop
    v_prev_policy := null;

    if v_continuity_status='CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT' then
      select f.*
        into v_prev_policy
      from public.alpha_hunter_profit_management_forward_v01 f
      where f.position_snapshot_id=v_prev_position_id
        and f.policy_id=v_policy.policy_id
      limit 1;
    end if;

    if v_prev_policy.observation_id is not null
       and v_prev_policy.shadow_state='TRIGGERED' then
      -- Once the shadow policy has exited, freeze its terminal evidence while
      -- the real position may continue to exist.
      v_running_favorable_mark := v_prev_policy.running_favorable_mark;
      v_running_favorable_pct := v_prev_policy.running_favorable_pct;
      v_policy_active := true;
      v_policy_activated_at := v_prev_policy.policy_activated_at_utc;
      v_shadow_stop := v_prev_policy.shadow_stop_price;
      v_shadow_state := 'TRIGGERED';
      v_trigger_now := false;
      v_trigger_at := v_prev_policy.shadow_trigger_at_utc;
      v_trigger_mark := v_prev_policy.shadow_trigger_observed_mark;
      v_trigger_stop := v_prev_policy.shadow_stop_at_trigger;

    else
      if v_prev_policy.observation_id is not null then
        if new.direction='LONG' then
          v_running_favorable_mark := greatest(
            v_prev_policy.running_favorable_mark,
            new.mark_price
          );
        else
          v_running_favorable_mark := least(
            v_prev_policy.running_favorable_mark,
            new.mark_price
          );
        end if;
      else
        v_running_favorable_mark := new.mark_price;
      end if;

      if new.direction='LONG' then
        v_running_favorable_pct :=
          100.0*(v_running_favorable_mark-v_anchor_entry_price)
          /v_anchor_entry_price;
      else
        v_running_favorable_pct :=
          100.0*(v_anchor_entry_price-v_running_favorable_mark)
          /v_anchor_entry_price;
      end if;

      v_policy_active := coalesce(v_prev_policy.policy_active,false)
        or v_running_favorable_pct >= v_policy.activation_favorable_pct;

      v_policy_activated_at := case
        when v_prev_policy.policy_activated_at_utc is not null
          then v_prev_policy.policy_activated_at_utc
        when v_policy_active
          then new.captured_at_utc
        else null
      end;

      if v_policy_active then
        if new.direction='LONG' then
          v_shadow_stop :=
            v_anchor_entry_price
            + v_policy.lock_fraction
              *(v_running_favorable_mark-v_anchor_entry_price);
        else
          v_shadow_stop :=
            v_anchor_entry_price
            - v_policy.lock_fraction
              *(v_anchor_entry_price-v_running_favorable_mark);
        end if;
      else
        v_shadow_stop := null;
      end if;

      v_trigger_now := (
        v_policy_active
        and v_shadow_stop is not null
        and (
          (new.direction='LONG' and new.mark_price <= v_shadow_stop)
          or
          (new.direction='SHORT' and new.mark_price >= v_shadow_stop)
        )
      );

      if v_trigger_now then
        v_shadow_state := 'TRIGGERED';
        v_trigger_at := new.captured_at_utc;
        v_trigger_mark := new.mark_price;
        v_trigger_stop := v_shadow_stop;
      elsif v_policy_active then
        v_shadow_state := 'ACTIVE';
        v_trigger_at := null;
        v_trigger_mark := null;
        v_trigger_stop := null;
      else
        v_shadow_state := 'INACTIVE';
        v_trigger_at := null;
        v_trigger_mark := null;
        v_trigger_stop := null;
      end if;
    end if;

    v_observation_id := substr(
      encode(
        extensions.digest(
          'profit-management-forward-v0.1|observation|'
          || new.position_snapshot_id || '|' || v_policy.policy_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    );

    insert into public.alpha_hunter_profit_management_forward_v01(
      observation_id,
      position_snapshot_id,
      account_snapshot_id,
      captured_at_utc,
      episode_id,
      episode_started_at_utc,
      continuity_status,
      previous_position_snapshot_id,
      symbol,
      direction,
      quantity,
      average_entry,
      mark_price,
      episode_entry_price,
      episode_initial_quantity,
      policy_id,
      activation_favorable_pct,
      lock_fraction,
      threshold_basis,
      running_favorable_mark,
      running_favorable_pct,
      policy_active,
      policy_activated_at_utc,
      shadow_stop_price,
      shadow_state,
      trigger_observed_on_this_snapshot,
      shadow_trigger_at_utc,
      shadow_trigger_observed_mark,
      shadow_stop_at_trigger,
      entry_changed_from_previous,
      quantity_changed_from_previous,
      evidence,
      forward_only,
      sampled_mark_limitation,
      counterfactual_fee_claim_permitted,
      counterfactual_funding_claim_permitted,
      counterfactual_net_pnl_claim_permitted,
      management_change_permitted,
      stop_change_permitted,
      target_change_permitted,
      promotion_permitted,
      model_version,
      shadow_only,
      trade_permission,
      order_path
    ) values (
      v_observation_id,
      new.position_snapshot_id,
      new.account_snapshot_id,
      new.captured_at_utc,
      v_anchor_episode_id,
      v_anchor_episode_started_at,
      v_continuity_status,
      v_prev_position_id,
      new.symbol,
      new.direction,
      new.quantity,
      new.average_entry,
      new.mark_price,
      v_anchor_entry_price,
      v_anchor_initial_quantity,
      v_policy.policy_id,
      v_policy.activation_favorable_pct,
      v_policy.lock_fraction,
      v_policy.threshold_basis,
      v_running_favorable_mark,
      v_running_favorable_pct,
      v_policy_active,
      v_policy_activated_at,
      v_shadow_stop,
      v_shadow_state,
      v_trigger_now,
      v_trigger_at,
      v_trigger_mark,
      v_trigger_stop,
      v_entry_changed,
      v_quantity_changed,
      jsonb_build_object(
        'source','CANONICAL_OPEN_POSITION_SNAPSHOT_TRIGGER',
        'account_source',v_current_source,
        'previous_account_snapshot_id',v_prev_account_id,
        'previous_position_snapshot_id',v_prev_position_id,
        'episode_identity_rule',
          'PREVIOUS_ACCOUNT_SNAPSHOT_SAME_SYMBOL_DIRECTION_AND_STABLE_ENTRY',
        'sampled_mark_is_not_tick_path',true,
        'no_historical_backfill',true,
        'no_exchange_call',true
      ),
      true,
      true,
      false,
      false,
      false,
      false,
      false,
      false,
      false,
      'profit-management-forward-v0.1',
      true,
      false,
      'NONE'
    )
    on conflict(position_snapshot_id,policy_id) do nothing;
  end loop;

  return new;

exception when others then
  -- Shadow-monitor failure must never block canonical account evidence.
  return new;
end;
$$;

revoke all on function private.alpha_hunter_materialize_profit_management_forward_v01()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_materialize_profit_management_forward_v01()
  to service_role;

drop trigger if exists trg_ah_materialize_profit_management_forward_v01
  on public.alpha_hunter_open_position_snapshots;
create trigger trg_ah_materialize_profit_management_forward_v01
after insert on public.alpha_hunter_open_position_snapshots
for each row execute function private.alpha_hunter_materialize_profit_management_forward_v01();


create or replace view public.alpha_hunter_profit_management_forward_current_v01
with (security_invoker=true,security_barrier=true)
as
select distinct on (episode_id,policy_id)
  observation_id,
  position_snapshot_id,
  account_snapshot_id,
  captured_at_utc,
  episode_id,
  episode_started_at_utc,
  continuity_status,
  symbol,
  direction,
  quantity,
  average_entry,
  mark_price,
  episode_entry_price,
  episode_initial_quantity,
  policy_id,
  activation_favorable_pct,
  lock_fraction,
  threshold_basis,
  running_favorable_mark,
  running_favorable_pct,
  policy_active,
  policy_activated_at_utc,
  shadow_stop_price,
  shadow_state,
  trigger_observed_on_this_snapshot,
  shadow_trigger_at_utc,
  shadow_trigger_observed_mark,
  shadow_stop_at_trigger,
  entry_changed_from_previous,
  quantity_changed_from_previous,
  forward_only,
  sampled_mark_limitation,
  management_change_permitted,
  stop_change_permitted,
  target_change_permitted,
  promotion_permitted,
  shadow_only,
  trade_permission,
  order_path
from public.alpha_hunter_profit_management_forward_v01
order by episode_id,policy_id,captured_at_utc desc,observation_id desc;

revoke all on public.alpha_hunter_profit_management_forward_current_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profit_management_forward_current_v01
  to service_role;


create or replace view public.alpha_hunter_profit_management_forward_coverage_v01
with (security_invoker=true,security_barrier=true)
as
with cfg as (
  select activated_at_utc
  from public.alpha_hunter_profit_management_forward_config_v01
  where config_id='profit-management-forward-v0.1'
),
expected as (
  select count(*)::bigint as position_snapshot_count
  from public.alpha_hunter_open_position_snapshots p,cfg
  where p.captured_at_utc >= cfg.activated_at_utc
),
actual as (
  select
    count(*)::bigint as observation_count,
    count(distinct position_snapshot_id)::bigint
      as covered_position_snapshot_count,
    count(*) filter(
      where captured_at_utc < (select activated_at_utc from cfg)
    )::bigint as preactivation_observation_violations,
    count(*) filter(where not forward_only)::bigint
      as forward_only_flag_violations,
    count(*) filter(where trade_permission)::bigint
      as trade_permission_violations,
    count(*) filter(where order_path<>'NONE')::bigint
      as order_path_violations
  from public.alpha_hunter_profit_management_forward_v01
)
select
  cfg.activated_at_utc,
  e.position_snapshot_count,
  e.position_snapshot_count*3 as expected_observation_count,
  a.covered_position_snapshot_count,
  a.observation_count,
  case
    when e.position_snapshot_count=0 then 100.0
    else 100.0*a.covered_position_snapshot_count/e.position_snapshot_count
  end as position_snapshot_coverage_pct,
  case
    when e.position_snapshot_count=0 then 100.0
    else 100.0*a.observation_count/(e.position_snapshot_count*3)
  end as policy_observation_coverage_pct,
  a.preactivation_observation_violations,
  a.forward_only_flag_violations,
  a.trade_permission_violations,
  a.order_path_violations,
  (
    a.preactivation_observation_violations=0
    and a.forward_only_flag_violations=0
    and a.trade_permission_violations=0
    and a.order_path_violations=0
    and a.covered_position_snapshot_count=e.position_snapshot_count
    and a.observation_count=e.position_snapshot_count*3
  ) as forward_monitoring_complete,
  false as management_change_permitted,
  false as promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from cfg
cross join expected e
cross join actual a;

revoke all on public.alpha_hunter_profit_management_forward_coverage_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profit_management_forward_coverage_v01
  to service_role;
