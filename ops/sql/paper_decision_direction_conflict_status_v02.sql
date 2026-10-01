-- Release 2.6 paper decision status alignment.

alter table public.alpha_hunter_paper_decisions_v01
  drop constraint if exists alpha_hunter_paper_decisions_v01_action_status_check;

alter table public.alpha_hunter_paper_decisions_v01
  add constraint alpha_hunter_paper_decisions_v01_action_status_check
  check (action_status in ('EXECUTE_NOW_PAPER','PLACE_LIMIT_PAPER','WAIT_FOR_TRIGGER','BLOCKED','BLOCKED_DIRECTION_CONFLICT'));
