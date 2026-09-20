-- Alpha Hunter forward missed-mover audit v0.1
--
-- Purpose:
--   Restore the nonstop missed-money/root-cause investigation from the
--   canonical forward answer-key without running another market scan.
--
-- Audit unit:
--   First observed 5% answer-key threshold event for each symbol/direction
--   episode. Repeated 5% rows belong to the same episode until there has been
--   a >24H gap in 5% answer-key evidence.
--
-- Anti-hindsight rule:
--   Root-cause classification uses ONLY canonical evidence timestamped before
--   the first observed 5% answer-key event. Later answer-key magnitude is not
--   used to decide FOUND/MISSED/root cause.
--
-- This is investigation evidence only. It cannot grant READY, T0, trade
-- permission, threshold changes, or production promotion.

create table if not exists public.alpha_hunter_forward_missed_mover_audit_v01 (
  audit_id text primary key,
  episode_id text not null unique,
  first_5pct_event_id text not null unique,
  audited_at_utc timestamptz not null default clock_timestamp(),

  symbol text not null,
  mover_direction text not null check(mover_direction in ('UP','DOWN')),
  expected_trade_direction text not null
    check(expected_trade_direction in ('LONG','SHORT')),

  first_5pct_seen_at_utc timestamptz not null,
  first_5pct_move_pct double precision not null,
  first_5pct_price double precision not null,
  first_5pct_quote_volume_24h double precision,
  first_5pct_liquidity_pass boolean,

  lookback_start_utc timestamptz not null,
  pre5_universe_observation_count integer not null default 0,
  pre5_universe_first_seen_at_utc timestamptz,
  pre5_universe_last_seen_at_utc timestamptz,
  first_prefilter_eligible_at_utc timestamptz,
  first_deep_scan_selected_at_utc timestamptz,

  pre5_signal_observation_count integer not null default 0,
  first_signal_at_utc timestamptz,
  latest_signal_at_utc timestamptz,
  first_expected_direction_at_utc timestamptz,
  first_opposite_direction_at_utc timestamptz,
  expected_direction_seen boolean not null default false,
  opposite_direction_seen boolean not null default false,
  any_execution_permission boolean not null default false,
  max_expected_direction_execution_rr double precision,

  latest_pre5_signal_direction text,
  latest_pre5_signal_state text,
  latest_pre5_opportunity_timing text,
  latest_pre5_market_phase text,
  latest_pre5_execution_permission boolean,
  latest_pre5_execution_rr double precision,
  latest_pre5_execution_reason text,

  latest_expected_direction_signal_at_utc timestamptz,
  latest_expected_direction_state text,
  latest_expected_direction_opportunity_timing text,
  latest_expected_direction_market_phase text,
  latest_expected_direction_execution_permission boolean,
  latest_expected_direction_execution_rr double precision,
  latest_expected_direction_execution_reason text,

  found_class text not null,
  root_cause_class text not null,
  root_cause_detail text not null,
  measurement_quality text not null,

  root_cause_uses_only_pre5_evidence boolean not null default true
    check(root_cause_uses_only_pre5_evidence=true),
  post_event_magnitude_used_for_classification boolean not null default false
    check(post_event_magnitude_used_for_classification=false),
  future_outcome_used_for_classification boolean not null default false
    check(future_outcome_used_for_classification=false),

  scientific_role text not null default
    'FORWARD_ANSWER_KEY_ROOT_CAUSE_AUDIT',
  model_version text not null default 'forward-missed-mover-audit-v0.1',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_forward_missed_mover_audit_v01
  enable row level security;

revoke all on table public.alpha_hunter_forward_missed_mover_audit_v01
  from public,anon,authenticated,service_role;

grant select on table public.alpha_hunter_forward_missed_mover_audit_v01
  to service_role;

drop trigger if exists trg_ah_forward_missed_mover_audit_append_only
  on public.alpha_hunter_forward_missed_mover_audit_v01;
create trigger trg_ah_forward_missed_mover_audit_append_only
before update or delete on public.alpha_hunter_forward_missed_mover_audit_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create index if not exists idx_ah_forward_missed_mover_audit_time
  on public.alpha_hunter_forward_missed_mover_audit_v01(
    first_5pct_seen_at_utc
  );

create index if not exists idx_ah_forward_missed_mover_audit_root
  on public.alpha_hunter_forward_missed_mover_audit_v01(
    root_cause_class,found_class
  );


create or replace function private.alpha_hunter_capture_forward_missed_mover_audit_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_inserted integer := 0;
begin
  with five_pct as (
    select
      a.event_id,
      a.symbol,
      a.direction,
      a.observed_at_utc,
      a.current_24h_move_pct,
      a.last_price,
      a.quote_volume_24h,
      a.liquidity_pass,
      lag(a.observed_at_utc) over(
        partition by a.symbol,a.direction
        order by a.observed_at_utc,a.event_id
      ) as previous_5pct_at
    from public.alpha_hunter_big_mover_answer_key a
    where a.threshold_pct=5
      and a.shadow_only=true
      and a.trade_permission=false
  ),
  episode_starts as (
    select
      f.*,
      pg_catalog.md5(
        'forward-missed-mover-episode-v0.1|'
        ||f.symbol||'|'||f.direction||'|'||f.observed_at_utc::text
      ) as episode_id
    from five_pct f
    where f.previous_5pct_at is null
       or f.observed_at_utc-f.previous_5pct_at>interval '24 hours'
  ),
  pending as (
    select e.*
    from episode_starts e
    where not exists (
      select 1
      from public.alpha_hunter_forward_missed_mover_audit_v01 x
      where x.episode_id=e.episode_id
    )
    order by e.observed_at_utc desc,e.symbol,e.direction
    limit 250
  ),
  enriched as (
    select
      p.*,
      case when p.direction='UP' then 'LONG' else 'SHORT' end
        as expected_trade_direction,

      u.universe_count,
      u.first_seen_at,
      u.last_seen_at,
      u.first_prefilter_at,
      u.first_deep_scan_at,

      s.signal_count,
      s.first_signal_at,
      s.latest_signal_at,
      s.first_expected_direction_at,
      s.first_opposite_direction_at,
      coalesce(s.expected_direction_seen,false) as expected_direction_seen,
      coalesce(s.opposite_direction_seen,false) as opposite_direction_seen,
      coalesce(s.any_execution_permission,false) as any_execution_permission,
      s.max_expected_direction_rr,

      ls.effective_direction as latest_signal_direction,
      ls.state as latest_signal_state,
      ls.opportunity_timing as latest_opportunity_timing,
      ls.market_phase as latest_market_phase,
      ls.execution_permission as latest_execution_permission,
      ls.execution_rr as latest_execution_rr,
      ls.execution_reason as latest_execution_reason,

      es.signal_at as expected_signal_at,
      es.state as expected_signal_state,
      es.opportunity_timing as expected_opportunity_timing,
      es.market_phase as expected_market_phase,
      es.execution_permission as expected_execution_permission,
      es.execution_rr as expected_execution_rr,
      es.execution_reason as expected_execution_reason
    from pending p

    left join lateral (
      select
        count(*)::integer as universe_count,
        min(observed_at_utc) as first_seen_at,
        max(observed_at_utc) as last_seen_at,
        min(observed_at_utc) filter(
          where prefilter_eligible=true
            and abs(change_24h_pct)<5.0
        ) as first_prefilter_at,
        min(observed_at_utc) filter(
          where deep_scan_selected=true
            and abs(change_24h_pct)<5.0
        ) as first_deep_scan_at
      from public.alpha_hunter_universe_hourly u
      where u.symbol=p.symbol
        and u.observed_at_utc<p.observed_at_utc
        and u.observed_at_utc>=p.observed_at_utc-interval '24 hours'
    ) u on true

    left join lateral (
      with pre as (
        select
          sf.captured_at_utc,
          case
            when sf.direction in ('LONG','SHORT') then sf.direction
            when upper(coalesce(sf.state,'')) like '%LONG%' then 'LONG'
            when upper(coalesce(sf.state,'')) like '%SHORT%' then 'SHORT'
          end as effective_direction,
          case
            when sf.source_payload#>>'{execution_setup,permission}' in ('true','false')
            then (sf.source_payload#>>'{execution_setup,permission}')::boolean
            else false
          end as execution_permission,
          case
            when sf.source_payload#>>'{execution_setup,rr}'
              ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
            then (sf.source_payload#>>'{execution_setup,rr}')::double precision
          end as execution_rr
        from public.alpha_hunter_signal_features sf
        where sf.symbol=p.symbol
          and sf.captured_at_utc<p.observed_at_utc
          and sf.captured_at_utc>=p.observed_at_utc-interval '24 hours'
          and (sf.source_payload->>'change_24h_pct')
            ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and abs((sf.source_payload->>'change_24h_pct')::double precision)<5.0
      )
      select
        count(*)::integer as signal_count,
        min(captured_at_utc) as first_signal_at,
        max(captured_at_utc) as latest_signal_at,
        min(captured_at_utc) filter(
          where effective_direction=case when p.direction='UP' then 'LONG' else 'SHORT' end
        ) as first_expected_direction_at,
        min(captured_at_utc) filter(
          where effective_direction=case when p.direction='UP' then 'SHORT' else 'LONG' end
        ) as first_opposite_direction_at,
        bool_or(
          effective_direction=case when p.direction='UP' then 'LONG' else 'SHORT' end
        ) as expected_direction_seen,
        bool_or(
          effective_direction=case when p.direction='UP' then 'SHORT' else 'LONG' end
        ) as opposite_direction_seen,
        bool_or(
          execution_permission
          and effective_direction=case when p.direction='UP' then 'LONG' else 'SHORT' end
        ) as any_execution_permission,
        max(execution_rr) filter(
          where effective_direction=case when p.direction='UP' then 'LONG' else 'SHORT' end
        ) as max_expected_direction_rr
      from pre
    ) s on true

    left join lateral (
      select
        sf.captured_at_utc as signal_at,
        case
          when sf.direction in ('LONG','SHORT') then sf.direction
          when upper(coalesce(sf.state,'')) like '%LONG%' then 'LONG'
          when upper(coalesce(sf.state,'')) like '%SHORT%' then 'SHORT'
        end as effective_direction,
        sf.state,
        sf.source_payload->>'opportunity_timing' as opportunity_timing,
        sf.source_payload->>'market_phase' as market_phase,
        case
          when sf.source_payload#>>'{execution_setup,permission}' in ('true','false')
          then (sf.source_payload#>>'{execution_setup,permission}')::boolean
        end as execution_permission,
        case
          when sf.source_payload#>>'{execution_setup,rr}'
            ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          then (sf.source_payload#>>'{execution_setup,rr}')::double precision
        end as execution_rr,
        sf.source_payload#>>'{execution_setup,reason}' as execution_reason
      from public.alpha_hunter_signal_features sf
      where sf.symbol=p.symbol
        and sf.captured_at_utc<p.observed_at_utc
        and sf.captured_at_utc>=p.observed_at_utc-interval '24 hours'
        and (sf.source_payload->>'change_24h_pct')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        and abs((sf.source_payload->>'change_24h_pct')::double precision)<5.0
      order by sf.captured_at_utc desc,sf.signal_id
      limit 1
    ) ls on true

    left join lateral (
      select
        sf.captured_at_utc as signal_at,
        sf.state,
        sf.source_payload->>'opportunity_timing' as opportunity_timing,
        sf.source_payload->>'market_phase' as market_phase,
        case
          when sf.source_payload#>>'{execution_setup,permission}' in ('true','false')
          then (sf.source_payload#>>'{execution_setup,permission}')::boolean
        end as execution_permission,
        case
          when sf.source_payload#>>'{execution_setup,rr}'
            ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          then (sf.source_payload#>>'{execution_setup,rr}')::double precision
        end as execution_rr,
        sf.source_payload#>>'{execution_setup,reason}' as execution_reason
      from public.alpha_hunter_signal_features sf
      where sf.symbol=p.symbol
        and sf.captured_at_utc<p.observed_at_utc
        and sf.captured_at_utc>=p.observed_at_utc-interval '24 hours'
        and (sf.source_payload->>'change_24h_pct')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        and abs((sf.source_payload->>'change_24h_pct')::double precision)<5.0
        and (
          case
            when sf.direction in ('LONG','SHORT') then sf.direction
            when upper(coalesce(sf.state,'')) like '%LONG%' then 'LONG'
            when upper(coalesce(sf.state,'')) like '%SHORT%' then 'SHORT'
          end
        )=case when p.direction='UP' then 'LONG' else 'SHORT' end
      order by sf.captured_at_utc desc,sf.signal_id
      limit 1
    ) es on true
  ),
  classified as (
    select
      e.*,
      case
        when coalesce(e.signal_count,0)=0
          and coalesce(e.universe_count,0)=0
          then 'NOT_AUDITABLE'
        when e.any_execution_permission
          then 'FOUND_EXECUTABLE_SHADOW'
        when e.expected_direction_seen
          then 'FOUND_DIRECTION_PREMOVE'
        when coalesce(e.signal_count,0)>0 and e.opposite_direction_seen
          then 'WRONG_DIRECTION_PREMOVE'
        when coalesce(e.signal_count,0)>0
          then 'FOUND_UNCONFIRMED_PREMOVE'
        when e.first_deep_scan_at is not null
          then 'DEEP_SCAN_EVIDENCE_GAP'
        when e.first_prefilter_at is not null
          then 'PREFILTERED_NOT_DEEP_SCANNED'
        else 'SEEN_NOT_PREFILTERED'
      end as found_class,

      case
        when coalesce(e.signal_count,0)=0
          and coalesce(e.universe_count,0)=0
          then 'DATA'
        when e.any_execution_permission
          then 'EXECUTION_HANDOFF'
        when e.expected_direction_seen
          and coalesce(e.expected_execution_reason,'') ilike '%rr_minimum_met%'
          then 'EXECUTION_RR'
        when e.expected_direction_seen
          and coalesce(e.expected_execution_reason,'') ilike '%Direction is not fully aligned%'
          then 'CONFIRMATION_TAX'
        when e.expected_direction_seen
          then 'EXECUTION'
        when coalesce(e.signal_count,0)>0 and e.opposite_direction_seen
          then 'DIRECTION'
        when coalesce(e.signal_count,0)>0
          then 'DIRECTION'
        when e.first_deep_scan_at is not null
          then 'DATA'
        when e.first_prefilter_at is not null
          then 'RANKING'
        else 'DISCOVERY'
      end as root_cause_class,

      case
        when coalesce(e.signal_count,0)=0
          and coalesce(e.universe_count,0)=0
          then 'No canonical pre-5% universe or signal evidence in the 24H lookback.'
        when e.any_execution_permission
          then 'A correct-direction pre-5% signal reached execution permission in shadow; downstream execution/handoff must be audited separately.'
        when e.expected_direction_seen
          and coalesce(e.expected_execution_reason,'') ilike '%rr_minimum_met%'
          then 'Correct direction existed before 5%, but the latest correct-direction execution setup failed the RR minimum.'
        when e.expected_direction_seen
          and coalesce(e.expected_execution_reason,'') ilike '%Direction is not fully aligned%'
          then 'Correct direction state existed before 5%, but legacy multi-timeframe direction alignment withheld execution.'
        when e.expected_direction_seen
          then 'Correct direction existed before 5%, but no pre-5% execution permission was recorded.'
        when coalesce(e.signal_count,0)>0 and e.opposite_direction_seen
          then 'Pre-5% deep-scan evidence existed but direction was opposite the later mover direction.'
        when coalesce(e.signal_count,0)>0
          then 'Pre-5% deep-scan evidence existed but no contemporaneous direction matched the later mover.'
        when e.first_deep_scan_at is not null
          then 'Universe evidence says deep-scan selected, but matching canonical signal-feature evidence is missing.'
        when e.first_prefilter_at is not null
          then 'Symbol passed the prefilter before 5% but was not represented in canonical deep-scan signal evidence.'
        else 'Symbol was observed before 5% but never passed the canonical prefilter in the 24H lookback.'
      end as root_cause_detail,

      case
        when coalesce(e.signal_count,0)>0 then 'SIGNAL_EVIDENCE_AVAILABLE'
        when coalesce(e.universe_count,0)>0 then 'UNIVERSE_EVIDENCE_ONLY'
        else 'NOT_AUDITABLE_NO_PREMOVE_EVIDENCE'
      end as measurement_quality
    from enriched e
  ),
  inserted as (
    insert into public.alpha_hunter_forward_missed_mover_audit_v01(
      audit_id,episode_id,first_5pct_event_id,
      symbol,mover_direction,expected_trade_direction,
      first_5pct_seen_at_utc,first_5pct_move_pct,first_5pct_price,
      first_5pct_quote_volume_24h,first_5pct_liquidity_pass,
      lookback_start_utc,
      pre5_universe_observation_count,pre5_universe_first_seen_at_utc,
      pre5_universe_last_seen_at_utc,first_prefilter_eligible_at_utc,
      first_deep_scan_selected_at_utc,
      pre5_signal_observation_count,first_signal_at_utc,latest_signal_at_utc,
      first_expected_direction_at_utc,first_opposite_direction_at_utc,
      expected_direction_seen,opposite_direction_seen,
      any_execution_permission,max_expected_direction_execution_rr,
      latest_pre5_signal_direction,latest_pre5_signal_state,
      latest_pre5_opportunity_timing,latest_pre5_market_phase,
      latest_pre5_execution_permission,latest_pre5_execution_rr,
      latest_pre5_execution_reason,
      latest_expected_direction_signal_at_utc,
      latest_expected_direction_state,
      latest_expected_direction_opportunity_timing,
      latest_expected_direction_market_phase,
      latest_expected_direction_execution_permission,
      latest_expected_direction_execution_rr,
      latest_expected_direction_execution_reason,
      found_class,root_cause_class,root_cause_detail,measurement_quality,
      root_cause_uses_only_pre5_evidence,
      post_event_magnitude_used_for_classification,
      future_outcome_used_for_classification,
      shadow_only,trade_permission,t0_authorized,
      threshold_change_permitted,production_promotion_permitted,order_path
    )
    select
      pg_catalog.md5(
        'forward-missed-mover-audit-v0.1|'||c.episode_id
      ),
      c.episode_id,c.event_id,
      c.symbol,c.direction,c.expected_trade_direction,
      c.observed_at_utc,c.current_24h_move_pct,c.last_price,
      c.quote_volume_24h,c.liquidity_pass,
      c.observed_at_utc-interval '24 hours',
      coalesce(c.universe_count,0),c.first_seen_at,c.last_seen_at,
      c.first_prefilter_at,c.first_deep_scan_at,
      coalesce(c.signal_count,0),c.first_signal_at,c.latest_signal_at,
      c.first_expected_direction_at,c.first_opposite_direction_at,
      c.expected_direction_seen,c.opposite_direction_seen,
      c.any_execution_permission,c.max_expected_direction_rr,
      c.latest_signal_direction,c.latest_signal_state,
      c.latest_opportunity_timing,c.latest_market_phase,
      c.latest_execution_permission,c.latest_execution_rr,
      c.latest_execution_reason,
      c.expected_signal_at,c.expected_signal_state,
      c.expected_opportunity_timing,c.expected_market_phase,
      c.expected_execution_permission,c.expected_execution_rr,
      c.expected_execution_reason,
      c.found_class,c.root_cause_class,c.root_cause_detail,
      c.measurement_quality,
      true,false,false,
      true,false,false,false,false,'NONE'
    from classified c
    on conflict(episode_id) do nothing
    returning 1
  )
  select count(*) into v_inserted from inserted;

  return jsonb_build_object(
    'mode','FORWARD_ANSWER_KEY_ROOT_CAUSE_AUDIT',
    'rows_inserted',v_inserted,
    'second_market_scan_used',false,
    'root_cause_uses_only_pre5_evidence',true,
    'post_event_magnitude_used_for_classification',false,
    'future_outcome_used_for_classification',false,
    'shadow_only',true,
    'trade_permission',false,
    't0_authorized',false,
    'threshold_change_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_forward_missed_mover_audit_v01()
  from public,anon,authenticated;


create or replace view public.alpha_hunter_forward_missed_mover_audit_status_v01
with (security_invoker=true,security_barrier=true)
as
with five_pct as (
  select
    a.event_id,a.symbol,a.direction,a.observed_at_utc,
    lag(a.observed_at_utc) over(
      partition by a.symbol,a.direction
      order by a.observed_at_utc,a.event_id
    ) as previous_5pct_at
  from public.alpha_hunter_big_mover_answer_key a
  where a.threshold_pct=5
    and a.shadow_only=true
    and a.trade_permission=false
),
episodes as (
  select
    pg_catalog.md5(
      'forward-missed-mover-episode-v0.1|'
      ||symbol||'|'||direction||'|'||observed_at_utc::text
    ) as episode_id,
    observed_at_utc
  from five_pct
  where previous_5pct_at is null
     or observed_at_utc-previous_5pct_at>interval '24 hours'
),
audit as (
  select *
  from public.alpha_hunter_forward_missed_mover_audit_v01
)
select
  count(*)::bigint as answer_key_episode_count,
  count(a.audit_id)::bigint as audited_episode_count,
  count(*) filter(where a.audit_id is null)::bigint as unaudited_episode_count,
  max(a.audited_at_utc) as latest_audit_capture_at_utc,
  max(e.observed_at_utc) as latest_answer_key_episode_at_utc,
  count(a.audit_id) filter(
    where a.found_class='FOUND_EXECUTABLE_SHADOW'
  )::bigint as found_executable_shadow,
  count(a.audit_id) filter(
    where a.found_class='FOUND_DIRECTION_PREMOVE'
  )::bigint as found_direction_premove,
  count(a.audit_id) filter(
    where a.found_class='WRONG_DIRECTION_PREMOVE'
  )::bigint as wrong_direction_premove,
  count(a.audit_id) filter(
    where a.found_class='FOUND_UNCONFIRMED_PREMOVE'
  )::bigint as found_unconfirmed_premove,
  count(a.audit_id) filter(
    where a.found_class='PREFILTERED_NOT_DEEP_SCANNED'
  )::bigint as prefiltered_not_deep_scanned,
  count(a.audit_id) filter(
    where a.found_class='SEEN_NOT_PREFILTERED'
  )::bigint as seen_not_prefiltered,
  count(a.audit_id) filter(
    where a.found_class='NOT_AUDITABLE'
  )::bigint as not_auditable,
  count(a.audit_id) filter(where a.root_cause_class='DISCOVERY')
    ::bigint as discovery_root_causes,
  count(a.audit_id) filter(where a.root_cause_class='RANKING')
    ::bigint as ranking_root_causes,
  count(a.audit_id) filter(where a.root_cause_class='DIRECTION')
    ::bigint as direction_root_causes,
  count(a.audit_id) filter(where a.root_cause_class='CONFIRMATION_TAX')
    ::bigint as confirmation_tax_root_causes,
  count(a.audit_id) filter(where a.root_cause_class='EXECUTION_RR')
    ::bigint as execution_rr_root_causes,
  count(a.audit_id) filter(where a.root_cause_class='DATA')
    ::bigint as data_root_causes,
  false as second_market_scan_used,
  true as root_cause_uses_only_pre5_evidence,
  false as post_event_magnitude_used_for_classification,
  false as future_outcome_used_for_classification,
  true as shadow_only,
  false as trade_permission
from episodes e
left join audit a on a.episode_id=e.episode_id;


revoke all on public.alpha_hunter_forward_missed_mover_audit_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_forward_missed_mover_audit_status_v01
  to service_role;


do $$
begin
  if not exists(
    select 1 from cron.job
    where jobname='alpha-hunter-forward-missed-mover-audit-hourly'
  ) then
    perform cron.schedule(
      'alpha-hunter-forward-missed-mover-audit-hourly',
      '19 * * * *',
      'select private.alpha_hunter_capture_forward_missed_mover_audit_v01();'
    );
  end if;
end;
$$;
