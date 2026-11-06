\timing on
SET statement_timeout = 0;
BEGIN;
CREATE TEMP TABLE tmp_ba_annual AS
  SELECT * FROM business_vault.vw_ba_annual_indicators;
CREATE INDEX ON tmp_ba_annual (ags, year);
ANALYZE tmp_ba_annual;
EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO data_mart.fact_labour_market (
    geography_key,
    period_key,
    indicator_key,
    source_key,
    freq,
    isced11,
    sex,
    age,
    indicator_value,
    observation_status,
    months_available,
    is_complete
)
SELECT
    dg.geography_key,
    dp.period_key,
    di.indicator_key,
    ds.source_key,

    v.freq,
    v.isced11,
    v.sex,
    v.age,

    v.indicator_value,
    v.status,

    CASE
        WHEN v.source_system = 'BA'
         AND v.period_type = 'ANNUAL'
         AND v.indicator_code = 'BA_ARBEITSLOSE_AVG'
            THEN ba.arbeitslose_months_available

        WHEN v.source_system = 'BA'
         AND v.period_type = 'ANNUAL'
         AND v.indicator_code = 'BA_UNTERBESCHAEFTIGUNG_AVG'
            THEN ba.unterbeschaeftigung_months_available

        ELSE NULL
    END,

    CASE
        WHEN v.source_system = 'BA'
         AND v.period_type = 'ANNUAL'
         AND v.indicator_code = 'BA_ARBEITSLOSE_AVG'
            THEN ba.arbeitslose_year_complete

        WHEN v.source_system = 'BA'
         AND v.period_type = 'ANNUAL'
         AND v.indicator_code = 'BA_UNTERBESCHAEFTIGUNG_AVG'
            THEN ba.unterbeschaeftigung_year_complete

        WHEN v.source_system = 'BA'
            THEN TRUE

        ELSE NULL
    END

FROM business_vault.vw_labour_market_indicators AS v

JOIN data_mart.dim_geography AS dg
    ON dg.geography_system = v.source_system
   AND dg.geography_code = v.geography_code

JOIN data_mart.dim_source AS ds
    ON ds.source_code = v.source_system

JOIN data_mart.dim_indicator AS di
    ON di.source_code = v.source_system
   AND di.indicator_code = v.indicator_code
   AND di.unit = COALESCE(v.unit, 'UNKNOWN')

JOIN data_mart.dim_period AS dp
    ON dp.period_code =
       CASE
           WHEN v.period_type = 'DECEMBER'
               THEN 'M:' || v.period_year::TEXT || '-12'
           ELSE 'Y:' || v.period_year::TEXT
       END

LEFT JOIN tmp_ba_annual AS ba
    ON v.source_system = 'BA'
   AND ba.ags = v.geography_code
   AND ba.year = v.period_year

ON CONFLICT ON CONSTRAINT uq_fact_labour_market_grain
DO UPDATE SET
    indicator_value = EXCLUDED.indicator_value,
    observation_status = EXCLUDED.observation_status,
    months_available = EXCLUDED.months_available,
    is_complete = EXCLUDED.is_complete,
    loaded_at = CURRENT_TIMESTAMP;
ROLLBACK;
