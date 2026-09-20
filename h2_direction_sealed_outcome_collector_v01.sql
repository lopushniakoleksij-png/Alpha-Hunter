-- Alpha Hunter H2 exact-1m sealed outcome collector v0.1
--
-- Collects future H2/legacy opportunity paths only after the full 24h window is due.
-- Sealed outcomes are never selectable by service_role. Only operational counts are exposed.

create table if not exists public.alpha_hunter_h2_direction_outcomes_sealed_v01 (
  outcome_id text primary key,
  evaluator_spec_id text not null
    check(evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02'),
  h2_capture_id text not null unique
    references public.alpha_hunter_h2_direction_captures_v01(capture_id),
  legacy_capture_id text
    references public.alpha_hunter_h2_direction_captures_v01(capture_id),
  symbol text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  h2_decision_available_at_utc timestamptz not null,
  h2_anchor_at_utc timestamptz not null,
  h2_entry_open double precision not null check(h2_entry_open>0),
  legacy_decision_available_at_utc timestamptz,
  legacy_anchor_at_utc timestamptz,
  legacy_entry_open double precision,
  opportunity_end_at_utc timestamptz not null,
  h2_stop double precision,
  h2_target double precision,
  h2_reference_rr double precision,
  legacy_stop double precision,
  legacy_target double precision,
  legacy_reference_rr double precision,
  legacy_confirmation_present boolean not null,
  expected_minute_count integer not null check(expected_minute_count=1440),
  observed_minute_count integer not null check(observed_minute_count=1440),
  missing_minute_count integer not null check(missing_minute_count=0),
  terminal_candle_at_utc timestamptz not null,
  terminal_close double precision not null check(terminal_close>0),
  h2_first_stop_at_utc timestamptz,
  h2_first_target_at_utc timestamptz,
  h2_path_class text not null check(
    h2_path_class in (
      'REFERENCE_GEOMETRY_INVALID',
      'BOTH_TOUCHED_IN_SAME_1M_CANDLE',
      'STOP_FIRST','TARGET_FIRST','NEITHER'
    )
  ),
  h2_false_start boolean,
  h2_gross_r_pre_cost double precision,
  legacy_first_stop_at_utc timestamptz,
  legacy_first_target_at_utc timestamptz,
  legacy_path_class text not null check(
    legacy_path_class in (
      'NO_TRADE',
      'REFERENCE_GEOMETRY_INVALID',
      'BOTH_TOUCHED_IN_SAME_1M_CANDLE',
      'STOP_FIRST','TARGET_FIRST','NEITHER'
    )
  ),
  legacy_false_start boolean,
  legacy_gross_r_pre_cost double precision,
  cost_model_applied boolean not null default false check(cost_model_applied=false),
  cost_model_id text,
  h2_realistic_net_r double precision,
  legacy_realistic_net_r double precision,
  realistic_net_r_delta double precision,
  economic_metric_status text not null
    check(economic_metric_status='SEALED_PRE_COST_PATH_ONLY_COST_MODEL_REQUIRED_AT_FREEZE'),
  measurement_source text not null
    check(measurement_source='BITGET_PUBLIC_V3_1M_CANDLES_TWO_12H_PAGES'),
  exact_anchor_alignment_required boolean not null default true
    check(exact_anchor_alignment_required=true),
  exact_intrabar_order_claim_permitted boolean not null default false
    check(exact_intrabar_order_claim_permitted=false),
  reference_price_is_fill_claim boolean not null default false
    check(reference_price_is_fill_claim=false),
  outcome_evidence_sealed boolean not null default true
    check(outcome_evidence_sealed=true),
  h2_source_evidence_hash text not null check(h2_source_evidence_hash ~ '^[0-9a-f]{64}$'),
  legacy_source_evidence_hash text,
  result_hash text not null check(result_hash ~ '^[0-9a-f]{64}$'),
  evaluator_version text not null
    check(evaluator_version='h2-direction-sealed-outcome-collector-v0.1'),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(
    cost_model_id is null
    and h2_realistic_net_r is null
    and legacy_realistic_net_r is null
    and realistic_net_r_delta is null
  ),
  check(opportunity_end_at_utc=h2_anchor_at_utc+interval '24 hours')
);

create table if not exists public.alpha_hunter_h2_direction_sealed_failures_v01 (
  failure_id text primary key,
  evaluator_spec_id text not null,
  h2_capture_id text,
  symbol text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  failure_class text not null,
  error_message text not null,
  evaluator_version text not null
    check(evaluator_version='h2-direction-sealed-outcome-collector-v0.1'),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

create table if not exists public.alpha_hunter_h2_direction_sealed_collection_status_v01 (
  status_id text primary key
    check(status_id='AH-H2-DIRECTION-SEALED-COLLECTION-V01'),
  evaluator_spec_id text not null,
  last_run_at_utc timestamptz,
  due_anchor_count bigint not null default 0,
  sealed_outcome_set_count bigint not null default 0,
  failure_event_count bigint not null default 0,
  latest_failure_at_utc timestamptz,
  collection_status text not null default 'WAITING_FOR_FIRST_24H_HORIZON',
  primary_results_exposed boolean not null default false check(primary_results_exposed=false),
  outcome_access_permitted boolean not null default false check(outcome_access_permitted=false),
  confirmatory_analysis_permitted boolean not null default false check(confirmatory_analysis_permitted=false),
  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  updated_at_utc timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_h2_direction_outcomes_sealed_v01 enable row level security;
alter table public.alpha_hunter_h2_direction_sealed_failures_v01 enable row level security;
alter table public.alpha_hunter_h2_direction_sealed_collection_status_v01 enable row level security;

revoke all on public.alpha_hunter_h2_direction_outcomes_sealed_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_h2_direction_sealed_failures_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_h2_direction_sealed_collection_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_direction_sealed_collection_status_v01
  to service_role;

drop trigger if exists trg_ah_h2_outcomes_sealed_append_only
  on public.alpha_hunter_h2_direction_outcomes_sealed_v01;
create trigger trg_ah_h2_outcomes_sealed_append_only
before update or delete on public.alpha_hunter_h2_direction_outcomes_sealed_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_h2_sealed_failures_append_only
  on public.alpha_hunter_h2_direction_sealed_failures_v01;
create trigger trg_ah_h2_sealed_failures_append_only
before update or delete on public.alpha_hunter_h2_direction_sealed_failures_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

insert into public.alpha_hunter_h2_direction_sealed_collection_status_v01(
  status_id,evaluator_spec_id
) values (
  'AH-H2-DIRECTION-SEALED-COLLECTION-V01',
  'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02'
)
on conflict(status_id) do nothing;

create or replace function private.alpha_hunter_run_h2_direction_sealed_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  r record;
  v_legacy_capture_id text;
  v_legacy_decision timestamptz;
  v_legacy_anchor timestamptz;
  v_legacy_entry double precision;
  v_legacy_stop double precision;
  v_legacy_target double precision;
  v_legacy_source_hash text;
  v_legacy_present boolean;
  v_end timestamptz;
  v_page1_end timestamptz;
  v_page2_start timestamptz;
  v_last_minute timestamptz;
  v_url1 text;
  v_url2 text;
  v_status1 integer;
  v_status2 integer;
  v_content1 text;
  v_content2 text;
  v_payload1 jsonb;
  v_payload2 jsonb;
  v_observed integer;
  v_missing integer;
  v_terminal_close double precision;
  v_h2_geometry_valid boolean;
  v_legacy_geometry_valid boolean;
  v_h2_rr double precision;
  v_legacy_rr double precision;
  v_h2_first_stop timestamptz;
  v_h2_first_target timestamptz;
  v_legacy_first_stop timestamptz;
  v_legacy_first_target timestamptz;
  v_h2_path text;
  v_legacy_path text;
  v_h2_false boolean;
  v_legacy_false boolean;
  v_h2_gross_r double precision;
  v_legacy_gross_r double precision;
  v_result_hash text;
  v_inserted integer;
  v_processed integer := 0;
  v_sealed integer := 0;
  v_failures integer := 0;
  v_due_count bigint := 0;
  v_total_sealed bigint := 0;
  v_total_failures bigint := 0;
  v_latest_failure timestamptz;
  v_err text;
begin
  if not exists(
    select 1
    from public.alpha_hunter_h2_direction_evaluator_specs_v02
    where evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02'
      and status='PREREGISTERED_LOCKED'
      and outcome_access_permitted=false
      and primary_results_exposed=false
      and confirmatory_analysis_permitted=false
  ) then
    raise exception 'active locked H2 evaluator v0.2 preregistration missing';
  end if;

  for r in
    with recursive eligible as (
      select c.*,a.reference_candle_at_utc as h2_anchor_at_utc,a.reference_open as h2_entry_open
      from public.alpha_hunter_h2_direction_captures_v01 c
      join public.alpha_hunter_h2_direction_anchor_prices_v01 a on a.capture_id=c.capture_id
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01'
        and c.h2_triggered=true and c.shadow_only=true and c.trade_permission=false
    ),
    seed as (
      select distinct on(symbol,direction) e.*
      from eligible e order by symbol,direction,decision_available_at_utc,capture_id
    ),
    cooldown as (
      select s.* from seed s
      union all
      select n.*
      from cooldown p
      join lateral (
        select e.* from eligible e
        where e.symbol=p.symbol and e.direction=p.direction
          and e.decision_available_at_utc>=p.decision_available_at_utc+interval '24 hours'
        order by e.decision_available_at_utc,e.capture_id limit 1
      ) n on true
    )
    select c.* from cooldown c
    where c.h2_anchor_at_utc+interval '24 hours'+interval '5 minutes'<=clock_timestamp()
      and not exists(
        select 1 from public.alpha_hunter_h2_direction_outcomes_sealed_v01 o
        where o.h2_capture_id=c.capture_id
      )
    order by c.h2_anchor_at_utc,c.capture_id
    limit 10
  loop
    v_processed := v_processed+1;
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended('H2_SEALED_V01|'||r.capture_id,0)
    );
    if exists(
      select 1 from public.alpha_hunter_h2_direction_outcomes_sealed_v01 o
      where o.h2_capture_id=r.capture_id
    ) then
      continue;
    end if;

    begin
      v_end := r.h2_anchor_at_utc+interval '24 hours';
      v_page1_end := r.h2_anchor_at_utc+interval '12 hours'-interval '1 minute';
      v_page2_start := r.h2_anchor_at_utc+interval '12 hours';
      v_last_minute := v_end-interval '1 minute';

      v_legacy_capture_id := null;
      v_legacy_decision := null;
      v_legacy_anchor := null;
      v_legacy_entry := null;
      v_legacy_stop := null;
      v_legacy_target := null;
      v_legacy_source_hash := null;

      select lc.capture_id,lc.decision_available_at_utc,
             la.reference_candle_at_utc,la.reference_open,
             lc.research_stop_15m,lc.research_target_4h,lc.source_evidence_hash
      into v_legacy_capture_id,v_legacy_decision,v_legacy_anchor,
           v_legacy_entry,v_legacy_stop,v_legacy_target,v_legacy_source_hash
      from public.alpha_hunter_h2_direction_captures_v01 lc
      join public.alpha_hunter_h2_direction_anchor_prices_v01 la
        on la.capture_id=lc.capture_id
      where lc.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01'
        and lc.symbol=r.symbol and lc.direction=r.direction
        and lc.legacy_scanner_aligned=true
        and lc.shadow_only=true and lc.trade_permission=false
        and la.reference_candle_at_utc>=r.h2_anchor_at_utc
        and la.reference_candle_at_utc<v_end
      order by la.reference_candle_at_utc,lc.capture_id
      limit 1;
      v_legacy_present := found;

      v_url1 := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=1000',
        extensions.urlencode(r.symbol::varchar),
        floor(extract(epoch from(r.h2_anchor_at_utc-interval '1 minute'))*1000)::bigint,
        floor(extract(epoch from v_page1_end)*1000)::bigint
      );
      v_url2 := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=1000',
        extensions.urlencode(r.symbol::varchar),
        floor(extract(epoch from(v_page2_start-interval '1 minute'))*1000)::bigint,
        floor(extract(epoch from v_last_minute)*1000)::bigint
      );

      select (x).status,(x).content into v_status1,v_content1
      from (select extensions.http_get(v_url1) x) q;
      select (x).status,(x).content into v_status2,v_content2
      from (select extensions.http_get(v_url2) x) q;

      if v_status1<>200 then raise exception 'BITGET_PAGE1_HTTP_STATUS:%',v_status1; end if;
      if v_status2<>200 then raise exception 'BITGET_PAGE2_HTTP_STATUS:%',v_status2; end if;
      v_payload1 := v_content1::jsonb;
      v_payload2 := v_content2::jsonb;
      if coalesce(v_payload1->>'code','')<>'00000' then
        raise exception 'BITGET_PAGE1_PAYLOAD_CODE:%',v_payload1->>'code';
      end if;
      if coalesce(v_payload2->>'code','')<>'00000' then
        raise exception 'BITGET_PAGE2_PAYLOAD_CODE:%',v_payload2->>'code';
      end if;

      with raw as (
        select value as bar from jsonb_array_elements(coalesce(v_payload1->'data','[]'::jsonb))
        union all
        select value as bar from jsonb_array_elements(coalesce(v_payload2->'data','[]'::jsonb))
      ),
      parsed as (
        select distinct on((bar->>0)::bigint)
          pg_catalog.to_timestamp((bar->>0)::double precision/1000.0) as ts,
          (bar->>1)::double precision as open_price,
          (bar->>2)::double precision as high_price,
          (bar->>3)::double precision as low_price,
          (bar->>4)::double precision as close_price
        from raw
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        order by (bar->>0)::bigint
      ),
      w as (
        select * from parsed where ts>=r.h2_anchor_at_utc and ts<=v_last_minute
      ),
      expected as (
        select g as ts from pg_catalog.generate_series(
          r.h2_anchor_at_utc,v_last_minute,interval '1 minute'
        ) g
      )
      select
        (select count(*)::integer from w),
        (select count(*)::integer from expected e where not exists(select 1 from w where w.ts=e.ts)),
        (select close_price from w where ts=v_last_minute limit 1)
      into v_observed,v_missing,v_terminal_close;

      if v_observed<>1440 or v_missing<>0 or v_terminal_close is null then
        raise exception 'INCOMPLETE_1M_COVERAGE expected=1440 observed=% missing=% terminal=%',
          v_observed,v_missing,v_terminal_close;
      end if;

      v_h2_geometry_valid := (
        r.h2_entry_open>0 and r.research_stop_15m is not null and r.research_target_4h is not null
        and (
          (r.direction='LONG' and r.research_stop_15m<r.h2_entry_open and r.research_target_4h>r.h2_entry_open)
          or
          (r.direction='SHORT' and r.research_stop_15m>r.h2_entry_open and r.research_target_4h<r.h2_entry_open)
        )
      );
      v_h2_rr := case when v_h2_geometry_valid and abs(r.h2_entry_open-r.research_stop_15m)>0
        then abs(r.research_target_4h-r.h2_entry_open)/abs(r.h2_entry_open-r.research_stop_15m) end;

      v_legacy_geometry_valid := case when not v_legacy_present then false else (
        v_legacy_entry>0 and v_legacy_stop is not null and v_legacy_target is not null
        and (
          (r.direction='LONG' and v_legacy_stop<v_legacy_entry and v_legacy_target>v_legacy_entry)
          or
          (r.direction='SHORT' and v_legacy_stop>v_legacy_entry and v_legacy_target<v_legacy_entry)
        )
      ) end;
      v_legacy_rr := case when v_legacy_geometry_valid and abs(v_legacy_entry-v_legacy_stop)>0
        then abs(v_legacy_target-v_legacy_entry)/abs(v_legacy_entry-v_legacy_stop) end;

      with raw as (
        select value as bar from jsonb_array_elements(coalesce(v_payload1->'data','[]'::jsonb))
        union all
        select value as bar from jsonb_array_elements(coalesce(v_payload2->'data','[]'::jsonb))
      ),
      parsed as (
        select distinct on((bar->>0)::bigint)
          pg_catalog.to_timestamp((bar->>0)::double precision/1000.0) as ts,
          (bar->>2)::double precision as high_price,
          (bar->>3)::double precision as low_price
        from raw
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        order by (bar->>0)::bigint
      ),
      w as (
        select * from parsed where ts>=r.h2_anchor_at_utc and ts<=v_last_minute
      )
      select
        min(ts) filter(where v_h2_geometry_valid and (
          (r.direction='LONG' and low_price<=r.research_stop_15m)
          or (r.direction='SHORT' and high_price>=r.research_stop_15m)
        )),
        min(ts) filter(where v_h2_geometry_valid and (
          (r.direction='LONG' and high_price>=r.research_target_4h)
          or (r.direction='SHORT' and low_price<=r.research_target_4h)
        )),
        min(ts) filter(where v_legacy_present and v_legacy_geometry_valid and ts>=v_legacy_anchor and (
          (r.direction='LONG' and low_price<=v_legacy_stop)
          or (r.direction='SHORT' and high_price>=v_legacy_stop)
        )),
        min(ts) filter(where v_legacy_present and v_legacy_geometry_valid and ts>=v_legacy_anchor and (
          (r.direction='LONG' and high_price>=v_legacy_target)
          or (r.direction='SHORT' and low_price<=v_legacy_target)
        ))
      into v_h2_first_stop,v_h2_first_target,v_legacy_first_stop,v_legacy_first_target
      from w;

      v_h2_path := case
        when not v_h2_geometry_valid then 'REFERENCE_GEOMETRY_INVALID'
        when v_h2_first_stop is not null and v_h2_first_target is not null and v_h2_first_stop=v_h2_first_target
          then 'BOTH_TOUCHED_IN_SAME_1M_CANDLE'
        when v_h2_first_stop is not null and (v_h2_first_target is null or v_h2_first_stop<v_h2_first_target)
          then 'STOP_FIRST'
        when v_h2_first_target is not null and (v_h2_first_stop is null or v_h2_first_target<v_h2_first_stop)
          then 'TARGET_FIRST'
        else 'NEITHER'
      end;
      v_h2_false := case
        when v_h2_path='REFERENCE_GEOMETRY_INVALID' then null
        when v_h2_path in ('STOP_FIRST','BOTH_TOUCHED_IN_SAME_1M_CANDLE') then true
        else false
      end;
      v_h2_gross_r := case
        when v_h2_path='REFERENCE_GEOMETRY_INVALID' then null
        when v_h2_path in ('STOP_FIRST','BOTH_TOUCHED_IN_SAME_1M_CANDLE') then -1.0
        when v_h2_path='TARGET_FIRST' then v_h2_rr
        when v_h2_path='NEITHER' and abs(r.h2_entry_open-r.research_stop_15m)>0 then
          case when r.direction='LONG'
            then (v_terminal_close-r.h2_entry_open)/abs(r.h2_entry_open-r.research_stop_15m)
            else (r.h2_entry_open-v_terminal_close)/abs(r.h2_entry_open-r.research_stop_15m)
          end
      end;

      if not v_legacy_present then
        v_legacy_path := 'NO_TRADE';
        v_legacy_false := false;
        v_legacy_gross_r := 0.0;
      else
        v_legacy_path := case
          when not v_legacy_geometry_valid then 'REFERENCE_GEOMETRY_INVALID'
          when v_legacy_first_stop is not null and v_legacy_first_target is not null
            and v_legacy_first_stop=v_legacy_first_target then 'BOTH_TOUCHED_IN_SAME_1M_CANDLE'
          when v_legacy_first_stop is not null
            and (v_legacy_first_target is null or v_legacy_first_stop<v_legacy_first_target) then 'STOP_FIRST'
          when v_legacy_first_target is not null
            and (v_legacy_first_stop is null or v_legacy_first_target<v_legacy_first_stop) then 'TARGET_FIRST'
          else 'NEITHER'
        end;
        v_legacy_false := case
          when v_legacy_path='REFERENCE_GEOMETRY_INVALID' then null
          when v_legacy_path in ('STOP_FIRST','BOTH_TOUCHED_IN_SAME_1M_CANDLE') then true
          else false
        end;
        v_legacy_gross_r := case
          when v_legacy_path='REFERENCE_GEOMETRY_INVALID' then null
          when v_legacy_path in ('STOP_FIRST','BOTH_TOUCHED_IN_SAME_1M_CANDLE') then -1.0
          when v_legacy_path='TARGET_FIRST' then v_legacy_rr
          when v_legacy_path='NEITHER' and abs(v_legacy_entry-v_legacy_stop)>0 then
            case when r.direction='LONG'
              then (v_terminal_close-v_legacy_entry)/abs(v_legacy_entry-v_legacy_stop)
              else (v_legacy_entry-v_terminal_close)/abs(v_legacy_entry-v_legacy_stop)
            end
        end;
      end if;

      v_result_hash := pg_catalog.encode(
        extensions.digest(
          jsonb_build_object(
            'evaluator_spec_id','AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02',
            'h2_capture_id',r.capture_id,'legacy_capture_id',v_legacy_capture_id,
            'symbol',r.symbol,'direction',r.direction,
            'h2_anchor_at',r.h2_anchor_at_utc,'h2_entry_open',r.h2_entry_open,
            'legacy_anchor_at',v_legacy_anchor,'legacy_entry_open',v_legacy_entry,
            'opportunity_end_at',v_end,
            'h2_stop',r.research_stop_15m,'h2_target',r.research_target_4h,'h2_reference_rr',v_h2_rr,
            'legacy_stop',v_legacy_stop,'legacy_target',v_legacy_target,'legacy_reference_rr',v_legacy_rr,
            'expected_minute_count',1440,'observed_minute_count',v_observed,'missing_minute_count',v_missing,
            'terminal_close',v_terminal_close,
            'h2_first_stop',v_h2_first_stop,'h2_first_target',v_h2_first_target,
            'h2_path_class',v_h2_path,'h2_false_start',v_h2_false,'h2_gross_r_pre_cost',v_h2_gross_r,
            'legacy_first_stop',v_legacy_first_stop,'legacy_first_target',v_legacy_first_target,
            'legacy_path_class',v_legacy_path,'legacy_false_start',v_legacy_false,
            'legacy_gross_r_pre_cost',v_legacy_gross_r,
            'h2_source_evidence_hash',r.source_evidence_hash,
            'legacy_source_evidence_hash',v_legacy_source_hash,
            'evaluator_version','h2-direction-sealed-outcome-collector-v0.1'
          )::text,'sha256'
        ),'hex'
      );

      insert into public.alpha_hunter_h2_direction_outcomes_sealed_v01(
        outcome_id,evaluator_spec_id,h2_capture_id,legacy_capture_id,symbol,direction,
        h2_decision_available_at_utc,h2_anchor_at_utc,h2_entry_open,
        legacy_decision_available_at_utc,legacy_anchor_at_utc,legacy_entry_open,
        opportunity_end_at_utc,h2_stop,h2_target,h2_reference_rr,
        legacy_stop,legacy_target,legacy_reference_rr,legacy_confirmation_present,
        expected_minute_count,observed_minute_count,missing_minute_count,
        terminal_candle_at_utc,terminal_close,
        h2_first_stop_at_utc,h2_first_target_at_utc,h2_path_class,h2_false_start,h2_gross_r_pre_cost,
        legacy_first_stop_at_utc,legacy_first_target_at_utc,legacy_path_class,
        legacy_false_start,legacy_gross_r_pre_cost,
        cost_model_applied,cost_model_id,h2_realistic_net_r,legacy_realistic_net_r,
        realistic_net_r_delta,economic_metric_status,
        measurement_source,exact_anchor_alignment_required,
        exact_intrabar_order_claim_permitted,reference_price_is_fill_claim,outcome_evidence_sealed,
        h2_source_evidence_hash,legacy_source_evidence_hash,result_hash,evaluator_version,
        shadow_only,trade_permission,production_promotion_permitted,order_path
      ) values (
        pg_catalog.md5('h2-sealed-outcome-v0.1|AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02|'||r.capture_id),
        'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02',
        r.capture_id,v_legacy_capture_id,r.symbol,r.direction,
        r.decision_available_at_utc,r.h2_anchor_at_utc,r.h2_entry_open,
        v_legacy_decision,v_legacy_anchor,v_legacy_entry,v_end,
        r.research_stop_15m,r.research_target_4h,v_h2_rr,
        v_legacy_stop,v_legacy_target,v_legacy_rr,v_legacy_present,
        1440,v_observed,v_missing,v_last_minute,v_terminal_close,
        v_h2_first_stop,v_h2_first_target,v_h2_path,v_h2_false,v_h2_gross_r,
        v_legacy_first_stop,v_legacy_first_target,v_legacy_path,v_legacy_false,v_legacy_gross_r,
        false,null,null,null,null,'SEALED_PRE_COST_PATH_ONLY_COST_MODEL_REQUIRED_AT_FREEZE',
        'BITGET_PUBLIC_V3_1M_CANDLES_TWO_12H_PAGES',true,false,false,true,
        r.source_evidence_hash,v_legacy_source_hash,v_result_hash,
        'h2-direction-sealed-outcome-collector-v0.1',true,false,false,'NONE'
      )
      on conflict(h2_capture_id) do nothing;
      get diagnostics v_inserted=row_count;
      v_sealed := v_sealed+v_inserted;
    exception when others then
      v_err := left(sqlerrm,1000);
      v_failures := v_failures+1;
      insert into public.alpha_hunter_h2_direction_sealed_failures_v01(
        failure_id,evaluator_spec_id,h2_capture_id,symbol,
        failure_class,error_message,evaluator_version,
        shadow_only,trade_permission,production_promotion_permitted,order_path
      ) values (
        pg_catalog.md5('h2-sealed-failure-v0.1|'||coalesce(r.capture_id,'NO_CAPTURE')||'|'||clock_timestamp()::text),
        'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02',r.capture_id,r.symbol,
        case
          when v_err like 'INCOMPLETE_1M_COVERAGE%' then 'INCOMPLETE_1M_COVERAGE'
          when v_err like 'BITGET_PAGE1_HTTP_STATUS:%' then 'BITGET_PAGE1_HTTP_ERROR'
          when v_err like 'BITGET_PAGE2_HTTP_STATUS:%' then 'BITGET_PAGE2_HTTP_ERROR'
          when v_err like 'BITGET_PAGE1_PAYLOAD_CODE:%' then 'BITGET_PAGE1_PAYLOAD_ERROR'
          when v_err like 'BITGET_PAGE2_PAYLOAD_CODE:%' then 'BITGET_PAGE2_PAYLOAD_ERROR'
          else 'SEALED_COLLECTOR_ERROR'
        end,
        v_err,'h2-direction-sealed-outcome-collector-v0.1',true,false,false,'NONE'
      );
    end;
  end loop;

  with recursive eligible as (
    select c.capture_id,c.symbol,c.direction,c.decision_available_at_utc,
           a.reference_candle_at_utc as h2_anchor_at_utc
    from public.alpha_hunter_h2_direction_captures_v01 c
    join public.alpha_hunter_h2_direction_anchor_prices_v01 a on a.capture_id=c.capture_id
    where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01' and c.h2_triggered=true
  ),
  seed as (
    select distinct on(symbol,direction) e.*
    from eligible e order by symbol,direction,decision_available_at_utc,capture_id
  ),
  cooldown as (
    select s.* from seed s
    union all
    select n.* from cooldown p
    join lateral (
      select e.* from eligible e
      where e.symbol=p.symbol and e.direction=p.direction
        and e.decision_available_at_utc>=p.decision_available_at_utc+interval '24 hours'
      order by e.decision_available_at_utc,e.capture_id limit 1
    ) n on true
  )
  select count(*)::bigint into v_due_count
  from cooldown
  where h2_anchor_at_utc+interval '24 hours'+interval '5 minutes'<=clock_timestamp();

  select count(*)::bigint into v_total_sealed
  from public.alpha_hunter_h2_direction_outcomes_sealed_v01;
  select count(*)::bigint,max(failed_at_utc) into v_total_failures,v_latest_failure
  from public.alpha_hunter_h2_direction_sealed_failures_v01;

  update public.alpha_hunter_h2_direction_sealed_collection_status_v01
  set last_run_at_utc=clock_timestamp(),
      due_anchor_count=v_due_count,
      sealed_outcome_set_count=v_total_sealed,
      failure_event_count=v_total_failures,
      latest_failure_at_utc=v_latest_failure,
      collection_status=case
        when v_due_count=0 then 'WAITING_FOR_FIRST_24H_HORIZON'
        when v_total_sealed>=v_due_count then 'SEALED_COLLECTION_CURRENT'
        else 'SEALED_COLLECTION_INCOMPLETE_RETRY_REQUIRED'
      end,
      updated_at_utc=clock_timestamp()
  where status_id='AH-H2-DIRECTION-SEALED-COLLECTION-V01';

  return jsonb_build_object(
    'mode','H2_EXACT_1M_SEALED_COLLECTION',
    'processed_due_anchors',v_processed,
    'sealed_outcomes_inserted',v_sealed,
    'failure_events_this_run',v_failures,
    'due_anchor_count',v_due_count,
    'sealed_outcome_set_count',v_total_sealed,
    'failure_event_count',v_total_failures,
    'primary_results_exposed',false,
    'outcome_access_permitted',false,
    'confirmatory_analysis_permitted',false,
    'cost_model_applied',false,
    't0_authorized',false,
    'threshold_change_permitted',false,
    'production_promotion_permitted',false,
    'shadow_only',true,'trade_permission',false,'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_run_h2_direction_sealed_v01()
  from public,anon,authenticated,service_role;

do $$
begin
  if not exists(
    select 1 from cron.job
    where jobname='alpha-hunter-h2-direction-sealed-outcome-hourly'
  ) then
    perform cron.schedule(
      'alpha-hunter-h2-direction-sealed-outcome-hourly',
      '28 * * * *',
      'select private.alpha_hunter_run_h2_direction_sealed_v01();'
    );
  end if;
end;
$$;

select private.alpha_hunter_run_h2_direction_sealed_v01();
