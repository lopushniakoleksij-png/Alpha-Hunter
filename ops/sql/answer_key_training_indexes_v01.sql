-- Alpha Hunter answer-key training performance indexes v0.1
--
-- Operations-only performance repair. Lives under ops/sql and is outside the
-- sealed V14 scientific fingerprint.
--
-- Root cause:
-- alpha_hunter_run_big_mover_shadow() timed out at 120s while building its
-- training evidence. The query shape is unchanged; this migration only adds
-- indexes matching existing run_id / captured_at / symbol+direction+time
-- predicates used by the current functions.
--
-- No strategy, threshold, label, feature, evidence, trade-permission or order
-- logic is changed.

create index if not exists idx_ah_features_run_captured_training_v01
  on public.alpha_hunter_signal_features(run_id,captured_at_utc desc);

create index if not exists idx_ah_features_captured_training_v01
  on public.alpha_hunter_signal_features(captured_at_utc desc);

create index if not exists idx_ah_missed_mover_training_ge5_v01
  on public.alpha_hunter_missed_mover_audit(
    symbol,mover_direction,audited_at_utc
  )
  where mover_threshold_pct>=5;

create index if not exists idx_ah_missed_mover_training_ge10_v01
  on public.alpha_hunter_missed_mover_audit(
    symbol,mover_direction,audited_at_utc
  )
  where mover_threshold_pct>=10;

create index if not exists idx_ah_answer_key_training_ge5_v01
  on public.alpha_hunter_big_mover_answer_key(
    symbol,direction,observed_at_utc
  )
  where threshold_pct>=5;

create index if not exists idx_ah_answer_key_training_ge10_v01
  on public.alpha_hunter_big_mover_answer_key(
    symbol,direction,observed_at_utc
  )
  where threshold_pct>=10;

create index if not exists idx_ah_answer_key_observed_at_v01
  on public.alpha_hunter_big_mover_answer_key(observed_at_utc desc);

analyze public.alpha_hunter_signal_features;
analyze public.alpha_hunter_missed_mover_audit;
analyze public.alpha_hunter_big_mover_answer_key;
