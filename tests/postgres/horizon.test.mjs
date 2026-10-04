import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const schema=read('horizon-schema.sql');
const migration=read('../../ops/sql/paper_horizon_successor_v09.sql');
const fixture=JSON.parse(read('horizon-case.json'));
async function setup(activate=true){
 const db=new PGlite();await db.exec(schema);await db.exec(migration);
 await db.exec(`insert into alpha_hunter_profitability_test_specs_v01(spec_id) values('R9');`);
 if(activate) await db.exec(`insert into alpha_hunter_paper_execution_activation_v09
 (activation_id,spec_id,protocol_version,activated_at_utc,runtime_verified_at_utc,
 admission_cutoff_at_utc,release_git_commit,scientific_fingerprint_sha256,evidence)
 values('PAPER_EXECUTION_R9','R9','paper-horizon-24h-v0.1','2026-10-01 00:00:01Z',
 '2026-10-01 00:00:00Z','2026-10-31 00:00:01Z',repeat('b',40),repeat('a',64),'{}');`);
 const p=fixture.position,s=fixture.snapshot;
 await db.query(`insert into alpha_hunter_paper_orders_v02(order_id,decision_id,symbol,direction,
 submitted_at_utc,quantity) values($1,$2,'TESTUSDT','LONG','2026-10-03 23:50Z',10)`,[p.entry_order_id,p.decision_id]);
 await db.query(`insert into alpha_hunter_paper_protection_open_v04
 (entry_order_id,decision_id,symbol,direction,entry_completed_at_utc,entry_quantity,
 stop_trigger_price,target_trigger_price) values($1,$2,'TESTUSDT','LONG',$3,10,9,15)`,
 [p.entry_order_id,p.decision_id,p.entry_completed_at_utc]);
 await db.query(`insert into alpha_hunter_paper_exit_attempts_v04
 (attempt_id,entry_order_id,observed_at_utc,outcome,evidence)
 values('prior',$1,$2,'NO_TRIGGER','{}')`,[p.entry_order_id,p.previous_exit_observed_at_utc]);
 await db.query(`insert into alpha_hunter_snapshots(run_id,collected_at_utc,payload)
 values($1,$2,$3)`,[s.run_id,s.collected_at_utc,JSON.stringify(s)]);
 return db;
}
const commit=(db,f=fixture)=>db.query(`select public.alpha_hunter_commit_paper_exit_reconciliation_v04($1,$2,$3)`,
 [JSON.stringify(f.attempts),JSON.stringify(f.fills),JSON.stringify(f.events)]);
test('horizon RPC persists executable exit with null protective ID and is replay-idempotent',async()=>{
 const db=await setup();try{
  await commit(db);await commit(db);
  const x=(await db.query('select * from alpha_hunter_paper_exit_fills_v04')).rows;
  assert.equal(x.length,1);assert.equal(x[0].triggered_protective_order_id,null);
  assert.equal(x[0].protection_type,'HORIZON_24H');assert.equal(Number(x[0].cross_price_reference),10);
  assert.equal((await db.query('select state from alpha_hunter_paper_events_v01')).rows[0].state,'HORIZON_CLOSED');
 }finally{await db.close();}
});
for(const defect of ['unactivated','prior-failure','noncanonical','late','insufficient-depth','stop-precedence','quantity']){
 test(`SQL rejects ${defect} horizon evidence atomically`,async()=>{
  const db=await setup(defect!=='unactivated');try{
   const f=structuredClone(fixture);
   if(defect==='prior-failure')await db.exec(`update alpha_hunter_paper_exit_attempts_v04 set evidence='{"horizon_integrity_failed":true}' where attempt_id='prior'`);
   if(defect==='noncanonical')await db.exec(`update alpha_hunter_snapshots set payload=jsonb_set(payload,'{validation_identity,run_source}','"WEB"')`);
   if(defect==='late')f.fills[0].filled_at_utc='2026-10-05T00:35:01+00:00';
   if(defect==='insufficient-depth')f.attempts[0].best_bid_size=1;
   if(defect==='stop-precedence')f.attempts[0].best_bid=8;
   if(defect==='quantity')f.fills[0].quantity=1;
   await assert.rejects(commit(db,f),/Horizon fill violates/);
   assert.equal((await db.query('select count(*) n from alpha_hunter_paper_exit_fills_v04')).rows[0].n,0);
   assert.equal((await db.query('select count(*) n from alpha_hunter_paper_exit_attempts_v04')).rows[0].n,1);
  }finally{await db.close();}
 });
}
test('activation absence keeps legacy protection visible without timeout policy',async()=>{
 const db=await setup(false);try{
  const rows=(await db.query('select * from alpha_hunter_paper_protection_horizon_open_v09')).rows;
  assert.equal(rows.length,1);assert.equal(rows[0].horizon_protocol,null);
  assert.equal((await db.query('select count(*) n from alpha_hunter_paper_profitability_status_v09')).rows[0].n,0);
 }finally{await db.close();}
});
test('unresolved and failed admitted orders remain in the cohort denominator',async()=>{
 const db=await setup();try{
  await db.exec(`insert into alpha_hunter_paper_orders_v02(order_id,decision_id,submitted_at_utc)
    values('failed','failed','2026-10-04');
    insert into alpha_hunter_paper_exit_attempts_v04(attempt_id,entry_order_id,evidence)
    values('failed','failed','{"horizon_integrity_failed":true}');`);
  const s=(await db.query('select * from alpha_hunter_paper_profitability_status_v09')).rows[0];
  assert.equal(s.admitted_orders,2);assert.equal(s.unresolved_orders,2);
  assert.equal(s.integrity_failed_orders,1);assert.equal(s.profitability_status,'BLOCKED_SUCCESSOR_INTEGRITY');
 }finally{await db.close();}
});
test('append-only halt closes admission but retains legacy and successor position protection',async()=>{
 const db=await setup();try{
  assert.equal((await db.query('select count(*) n from alpha_hunter_paper_admission_open_v09')).rows[0].n,1);
  await db.exec(`insert into alpha_hunter_paper_admission_halts_v09(activation_id,reason)
   values('PAPER_EXECUTION_R9','rollback containment');`);
  assert.equal((await db.query('select count(*) n from alpha_hunter_paper_admission_open_v09')).rows[0].n,0);
  assert.equal((await db.query('select count(*) n from alpha_hunter_paper_protection_horizon_open_v09')).rows[0].n,1);
  await assert.rejects(db.exec('delete from alpha_hunter_paper_admission_halts_v09'),/append only/);
 }finally{await db.close();}
});
