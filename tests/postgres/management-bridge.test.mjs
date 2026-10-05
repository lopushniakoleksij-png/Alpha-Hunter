import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const read=p=>readFileSync(new URL(p,import.meta.url),'utf8');
test('management bridge is owner-only, halted-cohort scoped, append-only and admission-neutral',async()=>{
 const db=new PGlite();try{
  await db.exec(read('horizon-schema.sql'));
  await db.exec('alter table alpha_hunter_paper_orders_v02 add primary key(order_id)');
  await db.exec(read('../../ops/sql/paper_horizon_successor_v09.sql'));
  await db.exec(read('../../ops/sql/r9_management_bridge_v01.sql'));
  await db.exec(`insert into alpha_hunter_profitability_test_specs_v01(spec_id) values('R9');
   insert into alpha_hunter_paper_execution_activation_v09
   (activation_id,spec_id,protocol_version,activated_at_utc,runtime_verified_at_utc,
    admission_cutoff_at_utc,release_git_commit,scientific_fingerprint_sha256,evidence)
   values('PAPER_EXECUTION_R9','R9','paper-horizon-24h-v0.1','2026-10-01 00:00:01Z',
   '2026-10-01Z','2026-10-31 00:00:01Z',repeat('b',40),repeat('a',64),'{}');
   insert into alpha_hunter_paper_orders_v02(order_id,submitted_at_utc)
   values('old','2026-09-30Z'),('r9','2026-10-02Z'),('later','2026-10-05Z');
   insert into alpha_hunter_paper_protection_open_v04(entry_order_id) values('r9');`);
  const approve=id=>db.query(`insert into alpha_hunter_r9_management_approvals_v01
   (entry_order_id,activation_id,scientific_fingerprint_sha256,release_git_commit,reason)
   values($1,'PAPER_EXECUTION_R9',repeat('c',64),repeat('d',40),'validated management handover')`,[id]);
  await assert.rejects(approve('r9'));
  await db.exec(`insert into alpha_hunter_paper_admission_halts_v09(activation_id,halted_at_utc,reason)
   values('PAPER_EXECUTION_R9','2026-10-04Z','controlled closure')`);
  await assert.rejects(approve('old'),/Management approval requires/);
  await assert.rejects(approve('later'),/Management approval requires/);
  await approve('r9');
  const p=(await db.query('select * from alpha_hunter_paper_protection_horizon_open_v09')).rows[0];
  assert.equal(p.horizon_scientific_fingerprint_sha256,'a'.repeat(64));
  assert.deepEqual(p.horizon_management_fingerprints,['c'.repeat(64)]);
  assert.equal((await db.query('select count(*) n from alpha_hunter_paper_admission_open_v09')).rows[0].n,0);
  await assert.rejects(db.exec('delete from alpha_hunter_r9_management_approvals_v01'),/append only/);
  const perms=(await db.query(`select
   has_table_privilege('service_role','alpha_hunter_r9_management_approvals_v01','INSERT') as can_insert,
   has_table_privilege('anon','alpha_hunter_r9_management_approvals_v01','SELECT') as anon_read,
   relrowsecurity from pg_class where oid='alpha_hunter_r9_management_approvals_v01'::regclass`)).rows[0];
  assert.deepEqual(perms,{can_insert:false,anon_read:false,relrowsecurity:true});
 }finally{await db.close();}
});
