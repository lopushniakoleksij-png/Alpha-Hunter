import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8');
const productionSource=read('successor-full-production-schema-fixture.sql');
const contract=read('successor-monitoring-cycle-seal-schema.sql');
const FINGERPRINT='50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834';
const C='2026-10-12T10:00:00Z', Q='2026-10-12T10:00:04Z';
const SYMS=['QUSDT','NMRUSDT'];
const POS=[
 {id:'p1',symbol:'QUSDT',direction:'LONG'},
 {id:'p2',symbol:'QUSDT',direction:'LONG'},
 {id:'p3',symbol:'NMRUSDT',direction:'SHORT'},
];
const seal=async(db,id)=>(
  await db.query('SELECT successor_shadow.try_seal_cycle($1) result',[id])
).rows[0].result;
const count=async(db,table,id)=>(
  await db.query(`SELECT count(*)::integer n FROM successor_shadow.${table} WHERE run_id=$1`,[id])
).rows[0].n;

async function database() {
  const db=new PGlite();
  await db.exec(productionSource);
  await db.exec(contract);
  return db;
}

// Registration and provenance are synthetic stand-ins for an *external* as-of
// inventory/FILL attestation. This is NOT a proof that live fill rows exist.
// The source symbol tables and trigger do match the captured production schema.
async function stage(db,options={}){
 const {
  run='synthetic-cycle-1', collected=C, quote=Q,
  manifest=SYMS, persisted=manifest, childReceipts=persisted,
  positions=POS, attempted=positions, basis='FILL_ATTESTED',
  basisSource='synthetic-immutable-fill-evidence', prior='2026-10-12T09:45:00Z',
  quoteSource='BITGET_PUBLIC_ALL_TICKERS', quoteSources=['BITGET_PUBLIC_ALL_TICKERS'],
  offsetSeconds=30, manifestCount=manifest.length,
  inventoryCount=positions.length,
 }=options;
 await db.exec('BEGIN');
 try{
  await db.query('INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES($1)',[run]);
  await db.query(`INSERT INTO successor_shadow.cycles(
   run_id,collected_at_utc,run_source,runtime_role,fingerprint,
   expected_symbol_count,expected_position_count,
   symbol_manifest_source,position_inventory_source,
   position_inventory_asof_utc,position_inventory_attested_complete,
   source_policy_id,approved_quote_sources,max_quote_offset_seconds)
   VALUES($1,$2,'RENDER_CRON','RENDER_CRON',$3,$4,$5,
   'synthetic-canonical-manifest','synthetic-independent-asof-inventory',
   $6,true,'synthetic-explicit-approved-source-policy',$7,$8)`,
   [run,collected,FINGERPRINT,manifestCount,inventoryCount,new Date(Date.parse(collected)-60000).toISOString(),quoteSources,offsetSeconds]);
  for(const symbol of manifest)
   await db.query(`INSERT INTO successor_shadow.expected_symbols(run_id,symbol) VALUES($1,$2)`,[run,symbol]);
  for(const symbol of persisted)
   await db.query(`INSERT INTO public.alpha_hunter_symbol_snapshots(
      run_id,symbol,collected_at_utc,payload) VALUES($1,$2,$3,'{}')`,[run,symbol,collected]);
  for(const symbol of childReceipts)
   await db.query(`INSERT INTO successor_shadow.committed_symbols(run_id,symbol,source_row_id)
      VALUES($1,$2,$3)`,[run,symbol,`source-child-${run}-${symbol}`]);
  for(const p of positions)
   await db.query(`INSERT INTO successor_shadow.expected_positions(
     run_id,entry_order_id,symbol,direction,basis_kind,basis_source_id,basis_qualified_at_utc)
     VALUES($1,$2,$3,$4,$5,$6,$7)`,
     [run,p.id,p.symbol,p.direction,basis,basisSource,prior]);
  for(const p of attempted)
   await db.query(`INSERT INTO successor_shadow.position_monitoring(
    run_id,entry_order_id,attempt_id,source_run_id,symbol,direction,
    outcome,quote_source,captured_at_utc,bid,ask,bid_size,ask_size)
    VALUES($1,$2,$3,$1,$4,$5,'NO_TRIGGER',$6,$7,1,1.01,10,7)`,
    [run,p.id,`attempt-${run}-${p.id}`,p.symbol,p.direction,quoteSource,quote]);
  await db.exec('COMMIT');
 }catch(e){await db.exec('ROLLBACK');throw e;}
 return run;
}

test('complete manifest + exact 3 as-of positions + 3 attempts: seal is structural only; immutable idempotent',async()=>{
 const db=await database();
 try{
  const run=await stage(db);
  assert.equal(await seal(db,run),'SEALED_LOCAL_STRUCTURAL_ONLY');
  assert.equal(await count(db,'completed_cycles',run),1);
  assert.equal(await seal(db,run),'ALREADY_SEALED_STRUCTURAL_ONLY');
  assert.equal(await count(db,'completed_cycles',run),1);
  const rows=(await db.query('SELECT * FROM successor_shadow.completed_cycles')).rows;
  assert.equal(rows[0].exchange_authority,false);
  assert.equal(rows[0].paper_authority,false);
  assert.equal(rows[0].scientific_pass_permitted,false);
  assert.equal(rows[0].status,'LOCAL_STRUCTURAL_COMPLETE_NOT_SCIENTIFIC_PASS');
  await assert.rejects(db.query(`INSERT INTO successor_shadow.expected_positions(
   run_id,entry_order_id,symbol,direction,basis_kind,basis_source_id,basis_qualified_at_utc)
   VALUES($1,'p4','QUSDT','LONG','FILL_ATTESTED','f4',$2)`,[run,'2026-10-12T09:59:00Z']),
   /ALREADY_SEALED/i);
  await assert.rejects(db.query(`UPDATE successor_shadow.expected_positions
   SET symbol='FAKEUSDT' WHERE run_id=$1`,[run]),/APPEND_ONLY/);
  await assert.rejects(db.query(`DELETE FROM successor_shadow.completed_cycles WHERE run_id=$1`,[run]),/APPEND_ONLY/);
 }finally{await db.close();}
});

test('parent-only scan (61 declared, 0 children and 0 paper attempts) NEVER gets a seal',async()=>{
 const db=await database();
 try{
  const run=await stage(db,{run:'parent-only-synthetic',
   manifestCount:61,manifest:SYMS,persisted:[],childReceipts:[],attempted:[]});
  assert.equal(await seal(db,run),'UNKNOWN_OR_INCOMPLETE_SYMBOL_STAGE');
  assert.equal(await count(db,'completed_cycles',run),0);
 }finally{await db.close();}
});

test('persisted child source FK and explicit symbol-manifest identity cannot be spoofed by a count',async()=>{
 const db=await database();
 try{
  await stage(db,{run:'symbol-missing-proof',childReceipts:['QUSDT']});
  assert.equal(await seal(db,'symbol-missing-proof'),'UNKNOWN_OR_INCOMPLETE_SYMBOL_STAGE');
  await assert.rejects(
   db.query(`INSERT INTO successor_shadow.committed_symbols(run_id,symbol,source_row_id)
    VALUES('symbol-missing-proof','FAKEUSDT','never-committed-source')`),
    /foreign key/i);
  await stage(db,{run:'symbol-fake-matches-count',manifest:SYMS,
     persisted:['QUSDT','FAKEUSDT'],childReceipts:['QUSDT','FAKEUSDT']});
  assert.equal(await seal(db,'symbol-fake-matches-count'),'UNKNOWN_OR_INCOMPLETE_SYMBOL_STAGE');
 }finally{await db.close();}
});

test('zero attempts or one missing position attempt can never seal even when quote exists for others',async()=>{
 const db=await database();
 try{
  await stage(db,{run:'none-attempted',attempted:[]});
  assert.equal(await seal(db,'none-attempted'),'UNKNOWN_OR_INCOMPLETE_POSITION_COUNT');
  await stage(db,{run:'one-attempt-missing',attempted:POS.slice(1)});
  assert.equal(await seal(db,'one-attempt-missing'),'UNKNOWN_OR_INCOMPLETE_POSITION_COUNT');
  assert.equal(await count(db,'completed_cycles','one-attempt-missing'),0);
 }finally{await db.close();}
});

test('position inventory cardinality and unexpected or duplicate attempts fail closed',async()=>{
 const db=await database();
 try{
  await stage(db,{run:'unproven-inventory',inventoryCount:4});
  assert.equal(await seal(db,'unproven-inventory'),'UNKNOWN_OR_INCOMPLETE_POSITION_COUNT');
  await stage(db,{run:'attempt-duplicates'});
  await assert.rejects(
   db.query(`INSERT INTO successor_shadow.position_monitoring(
    run_id,entry_order_id,attempt_id,source_run_id,symbol,direction,outcome,
    quote_source,captured_at_utc,bid,ask,bid_size,ask_size)
    VALUES('attempt-duplicates','p1','some-new-id','attempt-duplicates','QUSDT','LONG',
      'NO_TRIGGER','BITGET_PUBLIC_ALL_TICKERS',$1,1,1.1,3,4)`,[Q]),/duplicate key/i);
  await assert.rejects(
   db.query(`INSERT INTO successor_shadow.position_monitoring(
    run_id,entry_order_id,attempt_id,source_run_id,symbol,direction,outcome,
    quote_source,captured_at_utc,bid,ask,bid_size,ask_size)
    VALUES('attempt-duplicates','unrecognized-order','other-id','attempt-duplicates','QUSDT','LONG',
      'NO_TRIGGER','BITGET_PUBLIC_ALL_TICKERS',$1,1,1.1,3,4)`,[Q]),/foreign key/i);
 }finally{await db.close();}
});

test('explicit quote source allowlist, timestamp offset and 35m absolute continuity bound',async()=>{
 const db=await database();
 try{
  await stage(db,{run:'quote-source-unapproved',quoteSource:'UNKNOWN_VENDOR'});
  assert.equal(await seal(db,'quote-source-unapproved'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  await stage(db,{run:'quote-time-too-far',quote:'2026-10-12T10:01:00Z'});
  assert.equal(await seal(db,'quote-time-too-far'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  await stage(db,{run:'monitoring-gap-above-35m',prior:'2026-10-12T09:20:00Z'});
  assert.equal(await seal(db,'monitoring-gap-above-35m'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  await stage(db,{run:'quote-before-baseline',prior:'2026-10-12T10:00:05Z'});
  assert.equal(await seal(db,'quote-before-baseline'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  assert.equal(await count(db,'completed_cycles','monitoring-gap-above-35m'),0);
 }finally{await db.close();}
});

test('same-symbol concurrent strategy positions require separate per-order attempts',async()=>{
 const db=await database();
 try{
  await stage(db,{run:'duplicate-symbol-monitoring',attempted:[POS[0],POS[2]]});
  assert.equal(await seal(db,'duplicate-symbol-monitoring'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_COUNT');
  await db.query(`INSERT INTO successor_shadow.position_monitoring(
      run_id,entry_order_id,attempt_id,source_run_id,symbol,direction,outcome,
      quote_source,captured_at_utc,bid,ask,bid_size,ask_size)
      VALUES('duplicate-symbol-monitoring','p2','late-p2','duplicate-symbol-monitoring',
        'QUSDT','LONG','NO_TRIGGER','BITGET_PUBLIC_ALL_TICKERS',$1,1,1.01,10,7)`,[Q]);
  assert.equal(await seal(db,'duplicate-symbol-monitoring'),'SEALED_LOCAL_STRUCTURAL_ONLY');
 }finally{await db.close();}
});

test('subsequent cycle requires verifiable prior sealed receipt, exact identity and <=35m gap',async()=>{
 const db=await database();
 try{
  const first=await stage(db,{run:'first-sealed'});
  assert.equal(await seal(db,first),'SEALED_LOCAL_STRUCTURAL_ONLY');
  const second='second-sealed';
  await stage(db,{run:second,collected:'2026-10-12T10:20:00Z',quote:'2026-10-12T10:20:04Z',
    basis:'PRIOR_SEALED_CYCLE',basisSource:first,prior:Q});
  assert.equal(await seal(db,second),'SEALED_LOCAL_STRUCTURAL_ONLY');
  await stage(db,{run:'fabricated-prior',collected:'2026-10-12T10:20:00Z',
    quote:'2026-10-12T10:20:04Z',basis:'PRIOR_SEALED_CYCLE',
    basisSource:'never-sealed-run',prior:Q});
  assert.equal(await seal(db,'fabricated-prior'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  await stage(db,{run:'wrong-prior-clock',collected:'2026-10-12T10:20:00Z',
    quote:'2026-10-12T10:20:04Z',basis:'PRIOR_SEALED_CYCLE',
    basisSource:first,prior:'2026-10-12T10:00:03Z'});
  assert.equal(await seal(db,'wrong-prior-clock'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
  await stage(db,{run:'late-prior',collected:'2026-10-12T10:40:00Z',
    quote:'2026-10-12T10:40:04Z',basis:'PRIOR_SEALED_CYCLE',basisSource:first,prior:Q});
  assert.equal(await seal(db,'late-prior'),
    'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP');
 }finally{await db.close();}
});

test('structural permissions deny orders and public grants; never registers production routes',()=>{
 assert.match(contract,/35 minutes/g);
 assert.match(contract,/REFERENCES public\.alpha_hunter_symbol_snapshots\(run_id,symbol\)/);
 assert.match(contract,/REVOKE ALL ON ALL TABLES IN SCHEMA successor_shadow FROM PUBLIC/);
 assert.match(contract,/SECURITY INVOKER/);
 assert.match(contract,/scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK/);
 assert.match(contract,/exchange_authority boolean NOT NULL DEFAULT false CHECK/);
 assert.match(contract,/ON successor_shadow\.completed_cycles/);
 for(const forbidden of [/CREATE EXTENSION/i,/CREATE EVENT TRIGGER/i,/ALTER ROLE/i,
  /INSERT INTO public\.alpha_hunter_paper_/i,
  /UPDATE public\.alpha_hunter_/i,/DELETE FROM public\.alpha_hunter_/i,
  /CREATE TRIGGER .*ON public\.alpha_hunter_/i]){
  assert.equal(forbidden.test(contract),false,`prohibited SQL ${forbidden}`);
 }
});
