begin;

-- Paper reconciliation liquidity-source contract repair v0.1.
--
-- Root cause:
-- paper_reconciliation.py legitimately emits
-- BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE when a tracked symbol is
-- absent from the deep-scan set and a current public all-tickers quote is
-- captured read-only. The v0.2 fill table admitted only
-- BITGET_TOP_OF_BOOK_SNAPSHOT, so the atomic reconciliation RPC rolled back.
--
-- This migration changes only the evidence-source enum. It does not alter
-- fill prices, quantities, model rules, risk, permissions, or exchange authority.

alter table public.alpha_hunter_paper_fills_v02
  drop constraint if exists alpha_hunter_paper_fills_v02_liquidity_source_check;

alter table public.alpha_hunter_paper_fills_v02
  add constraint alpha_hunter_paper_fills_v02_liquidity_source_check
  check (
    liquidity_source in (
      'BITGET_TOP_OF_BOOK_SNAPSHOT',
      'BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE'
    )
  );

commit;
