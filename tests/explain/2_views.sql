\timing on
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM business_vault.vw_ba_annual_indicators;
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM business_vault.vw_labour_market_indicators;
