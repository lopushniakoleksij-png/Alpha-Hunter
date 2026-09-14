-- Alpha Hunter P0 hotfix: prevent the prospective early-mover cohort from being
-- starved by the global Money Scorecard maturation queue.
--
-- Safety invariants:
--   * preserves the existing 80-row evaluator budget
--   * does not create a second evaluator or scanner
--   * does not change outcome math, thresholds, permissions, or Bitget endpoints
--   * only changes ordering: clean v0.2 cohort first, then oldest global due rows

DO $hotfix$
DECLARE
  v_def text;
  v_old text := $old$
    order by o.horizon_due_at_utc,o.created_at
    limit 80
$old$;
  v_new text := $new$
    order by
      case when exists (
        select 1
        from public.alpha_hunter_early_mover_cohort e
        where e.scorecard_id = o.scorecard_id
          and e.capture_contract_version = 'prospective-early-mover-cohort-v0.2'
      ) then 0 else 1 end,
      o.horizon_due_at_utc,
      o.created_at
    limit 80
$new$;
BEGIN
  SELECT pg_get_functiondef(
    'private.alpha_hunter_run_big_mover_money_scorecard()'::regprocedure
  ) INTO v_def;

  IF position(v_new in v_def) > 0 THEN
    RETURN;
  END IF;

  IF position(v_old in v_def) = 0 THEN
    RAISE EXCEPTION 'scorecard evaluator ordering clause not found; refusing non-exact hotfix';
  END IF;

  v_def := replace(v_def, v_old, v_new);
  EXECUTE v_def;
END;
$hotfix$;

-- Fail closed if the exact priority contract is not present after installation.
DO $verify$
DECLARE
  v_def text;
BEGIN
  SELECT pg_get_functiondef(
    'private.alpha_hunter_run_big_mover_money_scorecard()'::regprocedure
  ) INTO v_def;

  IF position('prospective-early-mover-cohort-v0.2' in v_def) = 0
     OR position('limit 80' in lower(v_def)) = 0 THEN
    RAISE EXCEPTION 'P0 cohort priority verification failed';
  END IF;
END;
$verify$;
