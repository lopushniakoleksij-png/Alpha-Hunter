import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const sql=readFileSync(new URL('../../ops/sql/r8_reconciliation_required_containment_v01.sql',import.meta.url),'utf8');
const names={
  open:'alpha_hunter_paper_reconciliation_open_v08',
  exposure:'alpha_hunter_paper_active_exposure_members_v08',
  status:'alpha_hunter_r8_reconciliation_required_status_v01',
};
async function setup() {
  const db=new PGlite();
  await db.exec(`
    create role anon; create role authenticated; create role service_role;
    create table alpha_hunter_paper_reconciliation_attempts_v03(prior_state text);
    create table alpha_hunter_paper_execution_integrity_activation_v08(
      activation_id text,activated_at_utc timestamptz,maximum_entry_age_minutes integer);
    insert into alpha_hunter_paper_execution_integrity_activation_v08
      values('PAPER_EXECUTION_R8',now()-interval '1 day',35);
    create table alpha_hunter_paper_events_v01(
      decision_id text,sequence integer,state text,event_type text,
      occurred_at_utc timestamptz,created_at timestamptz default now());
    create table alpha_hunter_paper_fills_v02(order_id text,quantity numeric,fill_price numeric);
    create table alpha_hunter_paper_orders_v02(
      order_id text,decision_id text,symbol text,direction text,order_type text,
      limit_price numeric,quantity numeric,public_maker_fee_bps numeric,
      public_taker_fee_bps numeric,paper_only boolean,exchange_authority boolean,
      trade_permission boolean,order_path text,submitted_at_utc timestamptz);
    create table alpha_hunter_paper_decisions_v01(
      decision_id text,strategy_id text,stop_price numeric,target_price numeric);
    create table alpha_hunter_paper_entry_quarantine_v06(order_id text);
    create table alpha_hunter_paper_reconciliation_gate_v06(entry_reconciliation_permitted boolean);
    insert into alpha_hunter_paper_reconciliation_gate_v06 values(true);
    create table alpha_hunter_paper_protection_open_v04(
      entry_order_id text,decision_id text,symbol text,direction text);
    grant select on all tables in schema public to service_role;
  `);
  await db.exec(sql);
  return db;
}
async function order(db,id='rr',age=480,state='RECONCILIATION_REQUIRED',event='PAPER_FILL_EVIDENCE_INCOMPLETE') {
  await db.query(`insert into alpha_hunter_paper_orders_v02 values
    ($1,$1,$1,'SHORT','MARKET',null,10,2,6,true,false,false,'PAPER',now()-make_interval(mins=>$2))`,[id,age]);
  await db.query(`insert into alpha_hunter_paper_decisions_v01 values($1,'S8',11,5)`,[id]);
  await db.query(`insert into alpha_hunter_paper_events_v01(decision_id,sequence,state,event_type,occurred_at_utc)
    values($1,4,$2,$3,now()-interval '8 hours')`,[id,state,event]);
}
async function count(db,name) { return Number((await db.query(`select count(*) n from ${name}`)).rows[0].n); }

for(const gate of [false,null,'missing']) {
  test(`gate ${gate} blocks processing without hiding unresolved exposure`,async()=>{
    const db=await setup();
    try {
      await order(db);
      if(gate==='missing') await db.exec('delete from alpha_hunter_paper_reconciliation_gate_v06');
      else await db.query('update alpha_hunter_paper_reconciliation_gate_v06 set entry_reconciliation_permitted=$1',[gate]);
      assert.equal(await count(db,names.open),0);
      assert.equal(await count(db,names.exposure),1);
      const s=(await db.query(`select * from ${names.status}`)).rows[0];
      assert.equal(Number(s.reconciliation_required_zero_fill_orders),1);
      assert.equal(s.containment_status,'RECONCILIATION_BLOCKED_UNRESOLVED_ENTRIES_VISIBLE');
      assert.equal(s.entry_reconciliation_permitted,false);
      assert.equal(s.trade_permission,false);
    } finally {await db.close();}
  });
}

test('gate reopening restores worklist; explicit expiry releases exposure without creating fills',async()=>{
  const db=await setup();
  try {
    await order(db);
    await db.exec('update alpha_hunter_paper_reconciliation_gate_v06 set entry_reconciliation_permitted=false');
    assert.equal(await count(db,names.exposure),1);
    await db.exec('update alpha_hunter_paper_reconciliation_gate_v06 set entry_reconciliation_permitted=true');
    assert.equal(await count(db,names.open),1);
    assert.equal((await db.query(`select containment_status from ${names.status}`)).rows[0].containment_status,'EXPIRE_ON_NEXT_CANONICAL_RECONCILIATION');
    await db.exec(`insert into alpha_hunter_paper_events_v01(decision_id,sequence,state,event_type,occurred_at_utc)
      values('rr',5,'EXPIRED','PAPER_RECONCILIATION_REQUIRED_ENTRY_EXPIRED',now())`);
    assert.equal(await count(db,names.open),0); assert.equal(await count(db,names.exposure),0);
    assert.equal(await count(db,'alpha_hunter_paper_fills_v02'),0);
    assert.equal(await count(db,'alpha_hunter_paper_events_v01'),2);
  } finally {await db.close();}
});

test('recovery scope preserves fill, quarantine, activation and event restrictions',async()=>{
  const db=await setup();
  try {
    await order(db,'valid'); await order(db,'partial'); await order(db,'quarantined');
    await order(db,'old',1500); await order(db,'wrong-event',480,'RECONCILIATION_REQUIRED','OTHER_EVENT');
    await db.exec("insert into alpha_hunter_paper_fills_v02 values('partial',1,10)");
    await db.exec("insert into alpha_hunter_paper_entry_quarantine_v06 values('quarantined')");
    assert.deepEqual((await db.query(`select order_id from ${names.open}`)).rows,[{order_id:'valid'}]);
    assert.deepEqual((await db.query(`select order_id from ${names.exposure}`)).rows,[{order_id:'valid'}]);
  } finally {await db.close();}
});

test('recent submitted entry stays visible with closed gate and read-only role can inspect',async()=>{
  const db=await setup();
  try {
    await order(db,'submitted',10,'SUBMITTED','PAPER_ORDER_SUBMITTED');
    await db.exec('update alpha_hunter_paper_reconciliation_gate_v06 set entry_reconciliation_permitted=false');
    await db.exec('set role service_role');
    assert.equal(await count(db,names.open),0); assert.equal(await count(db,names.exposure),1);
    assert.equal((await db.query(`select has_table_privilege('service_role',
      'alpha_hunter_paper_reconciliation_inventory_v08','INSERT') p`)).rows[0].p,false);
    await db.exec('reset role');
    await db.exec(sql);
    assert.equal(await count(db,names.exposure),1);
  } finally {await db.close();}
});
