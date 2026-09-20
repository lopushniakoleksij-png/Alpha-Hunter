-- Alpha Hunter volume-growth ranking challenger v0.1
--
-- Purpose:
--   Test a zero-extra-scan challenger for the largest current live money leak:
--   prefilter-eligible symbols that never reach canonical deep-scan evidence.
--
-- Hypothesis-generating evidence BEFORE this forward challenger:
--   On 448 post-universe-restoration RANKING misses, using only information
--   available before the first 5% mover event:
--     production/static movement top-30 proxy recall: 54 / 448
--     hour-over-hour move-acceleration top-30 recall: 220 / 448
--     hour-over-hour quote-volume-growth top-30 recall: 297 / 448
--   These numbers are IN-SAMPLE DIAGNOSTIC ONLY and must not be reported as
--   forward validation or production lift.
--
-- Frozen challenger:
--   among currently prefilter-eligible symbols that have an immediately prior
--   universe observation 50-70 minutes earlier and positive quote volumes,
--   rank descending by ln(current_quote_volume / previous_quote_volume);
--   tie-break by symbol; select rank <= 30.
--
-- This view:
--   - uses only alpha_hunter_universe_hourly;
--   - does not query mover outcomes or answer-key tables;
--   - creates no exchange/API requests;
--   - does not change production deep_scan_selected;
--   - does not grant READY, T0/T1/T2, trade permission or production promotion.

create or replace view public.alpha_hunter_volume_growth_ranking_shadow_v01
with (security_invoker=true,security_barrier=true)
as
with base as (
  select
    u.observation_id,
    u.observed_at_utc,
    u.hour_bucket_utc,
    u.selection_run_id,
    u.symbol,
    u.last_price,
    u.change_24h_pct,
    u.quote_volume_24h,
    u.prefilter_eligible,
    u.deep_scan_selected as production_deep_scan_selected,
    u.measurement_quality,
    lag(u.observed_at_utc) over(
      partition by u.symbol order by u.observed_at_utc
    ) as previous_observed_at_utc,
    lag(u.quote_volume_24h) over(
      partition by u.symbol order by u.observed_at_utc
    ) as previous_quote_volume_24h
  from public.alpha_hunter_universe_hourly u
),
features as (
  select
    b.*,
    extract(epoch from (b.observed_at_utc-b.previous_observed_at_utc))
      as previous_gap_seconds,
    case
      when b.prefilter_eligible is true
       and b.previous_observed_at_utc is not null
       and extract(epoch from (b.observed_at_utc-b.previous_observed_at_utc))
             between 3000 and 4200
       and b.previous_quote_volume_24h>0
       and b.quote_volume_24h>0
      then ln(b.quote_volume_24h/b.previous_quote_volume_24h)
    end as volume_log_growth
  from base b
),
ranked as (
  select
    f.*,
    (
      f.prefilter_eligible is true
      and f.volume_log_growth is not null
      and f.volume_log_growth=f.volume_log_growth
    ) as ranking_eligible,
    case
      when f.prefilter_eligible is true
       and f.volume_log_growth is not null
       and f.volume_log_growth=f.volume_log_growth
      then row_number() over(
        partition by f.selection_run_id,
          (
            f.prefilter_eligible is true
            and f.volume_log_growth is not null
            and f.volume_log_growth=f.volume_log_growth
          )
        order by f.volume_log_growth desc,f.symbol
      )
    end as volume_growth_rank
  from features f
)
select
  observation_id,
  observed_at_utc,
  hour_bucket_utc,
  selection_run_id,
  symbol,
  last_price,
  change_24h_pct,
  quote_volume_24h,
  previous_observed_at_utc,
  previous_quote_volume_24h,
  previous_gap_seconds,
  volume_log_growth,
  volume_growth_rank,
  ranking_eligible,
  (ranking_eligible and volume_growth_rank<=30) as shadow_top30_selected,
  production_deep_scan_selected,
  case
    when not ranking_eligible then 'DATA_INSUFFICIENT_FOR_SHADOW_RANK'
    when volume_growth_rank<=30 then 'SHADOW_TOP30'
    else 'SHADOW_NOT_TOP30'
  end as shadow_status,
  measurement_quality,
  'VOLUME_GROWTH_TOP30_ZERO_EXTRA_SCAN'::text as challenger_rule,
  'HISTORICAL_DIAGNOSTIC_USED_ONLY_TO_SELECT_FORWARD_HYPOTHESIS'::text
    as historical_evidence_role,
  'SHADOW_RANKING_CHALLENGER_ONLY_NOT_EXECUTION_EDGE'::text as claim_ceiling,
  false as outcome_evidence_used,
  false as production_selector_changed,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  'volume-growth-ranking-shadow-v0.1'::text as model_version
from ranked;

revoke all on public.alpha_hunter_volume_growth_ranking_shadow_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_volume_growth_ranking_shadow_v01
  to service_role;
