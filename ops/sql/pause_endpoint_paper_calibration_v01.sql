-- Alpha Hunter paper-calibration semantic correction v0.1
--
-- Finding:
--   CAL-PAPER-WATCHSHORT-67-V01 was calibrated to
--   24H direction-adjusted endpoint return > 0.
--   That is NOT equivalent to a realistic paper-trade win.
--
-- Strict re-evaluation using signal outcome_class WIN/BIG_WIN:
--   training: 36 / 58 = 62.07%
--   holdout:   5 / 12 = 41.67%
--   combined: 41 / 70 = 58.57%
--
-- Therefore the 67.14% endpoint-positive estimate must not be used as a
-- paper-trade win probability. Pause the policy before any paper order exists.
--
-- Safety:
--   no live order path; no historical deletion; no trade mutation.

create table if not exists private.alpha_hunter_paper_calibration_corrections_v01 (
  correction_id text primary key,
  policy_id text not null,
  corrected_at_utc timestamptz not null default clock_timestamp(),
  original_outcome_definition text not null,
  corrected_outcome_definition text not null,
  original_point_estimate_pct double precision not null,
  strict_training_n integer not null,
  strict_training_wins integer not null,
  strict_training_win_pct double precision not null,
  strict_holdout_n integer not null,
  strict_holdout_wins integer not null,
  strict_holdout_win_pct double precision not null,
  strict_combined_n integer not null,
  strict_combined_wins integer not null,
  strict_combined_win_pct double precision not null,
  correction_reason text not null,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'PAPER_CALIBRATION_CORRECTION',
  paper_only boolean not null default true check(paper_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

do $block$
begin
  if exists(
    select 1
    from private.alpha_hunter_calibrated_paper_orders_v01
    where state in ('OPEN_PAPER','PENDING_LIMIT_PAPER')
  ) then
    raise exception 'cannot pause calibration policy while a paper order is active';
  end if;

  update private.alpha_hunter_calibrated_paper_policy_v01
  set status='PAUSED',
      evidence=evidence||jsonb_build_object(
        'strict_trade_win_recalibration',jsonb_build_object(
          'corrected_outcome_definition','SIGNAL_OUTCOME_CLASS_IN_WIN_BIG_WIN',
          'training_n',58,
          'training_wins',36,
          'training_win_rate_pct',62.0689655172414,
          'holdout_n',12,
          'holdout_wins',5,
          'holdout_win_rate_pct',41.6666666666667,
          'combined_n',70,
          'combined_wins',41,
          'combined_win_rate_pct',58.5714285714286,
          'paper_trade_win_probability_claim_permitted',false,
          'recalibration_status','FAILED_HOLDOUT_STABILITY'
        ),
        'pause_reason','ENDPOINT_POSITIVE_RATE_IS_NOT_PAPER_TRADE_WIN_RATE'
      ),
      updated_at=clock_timestamp()
  where policy_id='CAL-PAPER-WATCHSHORT-67-V01'
    and status='ACTIVE';
end;
$block$;

insert into private.alpha_hunter_paper_calibration_corrections_v01(
  correction_id,policy_id,
  original_outcome_definition,corrected_outcome_definition,
  original_point_estimate_pct,
  strict_training_n,strict_training_wins,strict_training_win_pct,
  strict_holdout_n,strict_holdout_wins,strict_holdout_win_pct,
  strict_combined_n,strict_combined_wins,strict_combined_win_pct,
  correction_reason,evidence,
  scientific_role,paper_only,trade_permission,
  production_promotion_permitted,order_path
) values (
  'PAPER-CAL-CORRECTION-20260929-V01',
  'CAL-PAPER-WATCHSHORT-67-V01',
  '24H_DIRECTION_ADJUSTED_ENDPOINT_RETURN_GT_0',
  'SIGNAL_OUTCOME_CLASS_IN_WIN_BIG_WIN',
  67.1428571428571,
  58,36,62.0689655172414,
  12,5,41.6666666666667,
  70,41,58.5714285714286,
  'ENDPOINT_POSITIVE_RATE_FAILED_AS_PROXY_FOR_REALISTIC_PAPER_TRADE_WIN',
  jsonb_build_object(
    'historical_endpoint_positive_estimate_pct',67.1428571428571,
    'strict_combined_win_pct',58.5714285714286,
    'holdout_strict_win_pct',41.6666666666667,
    'production_claim_permitted',false,
    'new_active_calibrated_policy_created',false,
    'next_gate','FIND_FORWARD_STABLE_STRICT_WIN_COHORT_OR_LEARN_FROM_REALISTIC_PAPER_OUTCOMES'
  ),
  'PAPER_CALIBRATION_CORRECTION',
  true,false,false,'NONE'
)
on conflict(correction_id) do nothing;

revoke all on private.alpha_hunter_paper_calibration_corrections_v01
from public,anon,authenticated,service_role;
grant select on private.alpha_hunter_paper_calibration_corrections_v01
to service_role;

-- The calibrated paper trigger remains installed but fail-closes because there
-- is no ACTIVE calibrated policy after this correction.
