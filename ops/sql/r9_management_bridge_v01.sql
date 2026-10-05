begin;
-- Install empty. Approval is per admitted order and exact future fingerprint.
-- This neither changes the frozen activation nor permits new admissions.
create table public.alpha_hunter_r9_management_approvals_v01 (
 entry_order_id text not null references public.alpha_hunter_paper_orders_v02(order_id),
 activation_id text not null references public.alpha_hunter_paper_admission_halts_v09(activation_id),
 scientific_fingerprint_sha256 text not null check(scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
 release_git_commit text not null check(release_git_commit ~ '^[a-f0-9]{40}$'),
 approved_at_utc timestamptz not null default clock_timestamp(),
 reason text not null check(length(reason)>0),
 primary key(entry_order_id,scientific_fingerprint_sha256)
);
alter table public.alpha_hunter_r9_management_approvals_v01 enable row level security;
revoke all on public.alpha_hunter_r9_management_approvals_v01 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r9_management_approvals_v01 to service_role;
create trigger trg_ah_r9_management_append_only before update or delete
 on public.alpha_hunter_r9_management_approvals_v01
 for each row execute function private.alpha_hunter_block_append_only_mutation();

create function private.alpha_hunter_validate_r9_management_v01()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if not exists (
  select 1 from public.alpha_hunter_paper_orders_v02 o
  join public.alpha_hunter_paper_execution_activation_v09 a
    on a.activation_id=new.activation_id
  join public.alpha_hunter_paper_admission_halts_v09 h using(activation_id)
  where o.order_id=new.entry_order_id
    and o.submitted_at_utc>a.activated_at_utc
    and o.submitted_at_utc<=h.halted_at_utc
    and new.approved_at_utc>=h.halted_at_utc
    and new.scientific_fingerprint_sha256<>a.scientific_fingerprint_sha256
 ) then raise exception 'Management approval requires an admitted order from halted R9 and a distinct runtime'; end if;
 return new;
end;
$$;
revoke all on function private.alpha_hunter_validate_r9_management_v01() from public,anon,authenticated,service_role;
create trigger trg_ah_r9_management_scope before insert
 on public.alpha_hunter_r9_management_approvals_v01
 for each row execute function private.alpha_hunter_validate_r9_management_v01();

-- Keep existing columns and joins intact. No historical membership is rewritten.
create or replace view public.alpha_hunter_paper_protection_horizon_open_v09
with(security_invoker=true,security_barrier=true) as
select p.*,a.protocol_version as horizon_protocol,
 a.scientific_fingerprint_sha256 as horizon_scientific_fingerprint_sha256,
 h.previous_exit_observed_at_utc,coalesce(h.horizon_integrity_failed,false) as horizon_integrity_failed,
 coalesce(h.unresolved_protective_evidence,false) as unresolved_protective_evidence,
 coalesce(m.fingerprints,array[]::text[]) as horizon_management_fingerprints
from public.alpha_hunter_paper_protection_open_v04 p
join public.alpha_hunter_paper_orders_v02 o on o.order_id=p.entry_order_id
left join public.alpha_hunter_paper_execution_activation_v09 a
 on o.submitted_at_utc>a.activated_at_utc
left join public.alpha_hunter_paper_horizon_history_v09 h using(entry_order_id)
left join lateral (
 select array_agg(b.scientific_fingerprint_sha256 order by b.scientific_fingerprint_sha256) as fingerprints
 from public.alpha_hunter_r9_management_approvals_v01 b
 where b.entry_order_id=p.entry_order_id and b.activation_id=a.activation_id
) m on true;
revoke all on public.alpha_hunter_paper_protection_horizon_open_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_protection_horizon_open_v09 to service_role;
commit;
