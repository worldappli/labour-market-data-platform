\timing on
SET statement_timeout = 0;
BEGIN;
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

LEFT JOIN business_vault.vw_ba_annual_indicators AS ba
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
BEGIN;
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

    NULL,
    NULL,
    NULL,
    NULL,

    x.indicator_value,
    NULL,
    NULL,
    TRUE

FROM raw_vault.sat_ba_labour_market AS s

JOIN raw_vault.hub_geography AS g
    ON g.geography_hk = s.geography_hk

JOIN data_mart.dim_geography AS dg
    ON dg.geography_system = 'BA'
   AND dg.geography_code = g.ags

JOIN data_mart.dim_source AS ds
    ON ds.source_code = 'BA'

CROSS JOIN LATERAL (
    VALUES
    (
        'BA_ARBEITSLOSE_MONTHLY'::VARCHAR,
        s.arbeitslose::NUMERIC
    ),
    (
        'BA_UNTERBESCHAEFTIGUNG_MONTHLY'::VARCHAR,
        s.unterbeschaeftigung::NUMERIC
    )
) AS x(indicator_code, indicator_value)

JOIN data_mart.dim_indicator AS di
    ON di.source_code = 'BA'
   AND di.indicator_code = x.indicator_code
   AND di.unit = 'PERSONS'

JOIN data_mart.dim_period AS dp
    ON dp.period_code =
       'M:' || TO_CHAR(s.period::DATE, 'YYYY-MM')

WHERE s.load_end_dts IS NULL
  AND x.indicator_value IS NOT NULL

ON CONFLICT ON CONSTRAINT uq_fact_labour_market_grain
DO UPDATE SET
    indicator_value = EXCLUDED.indicator_value,
    observation_status = EXCLUDED.observation_status,
    months_available = EXCLUDED.months_available,
    is_complete = EXCLUDED.is_complete,
    loaded_at = CURRENT_TIMESTAMP;
ROLLBACK;
