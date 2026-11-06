-- dim source
INSERT INTO data_mart.dim_source (
    source_code,
    source_name,
    source_description
)
VALUES
(
    'BA',
    'Bundesagentur für Arbeit',
    'Données administratives allemandes sur le chômage enregistré et le sous-emploi.'
),
(
    'EUROSTAT',
    'Eurostat',
    'Statistiques européennes harmonisées du marché du travail.'
)
ON CONFLICT (source_code) DO UPDATE SET
    source_name = EXCLUDED.source_name,
    source_description = EXCLUDED.source_description;

-- dim geography
INSERT INTO data_mart.dim_geography (
    geography_code,
    geography_system,
    geography_name,
    geography_level,
    ags,
    nuts1_code,
    nuts2_code,
    nuts3_code
)
SELECT DISTINCT
    geography_code,
    source_system,
    geography_name,
    geography_level,
    CASE
        WHEN source_system = 'BA'
        THEN geography_code
        ELSE NULL
    END,
    nuts1_code,
    nuts2_code,
    nuts3_code
FROM business_vault.vw_labour_market_indicators
WHERE geography_code IS NOT NULL
ON CONFLICT (geography_system, geography_code)
DO UPDATE SET
    geography_name  = EXCLUDED.geography_name,
    geography_level = EXCLUDED.geography_level,
    ags             = EXCLUDED.ags,
    nuts1_code      = EXCLUDED.nuts1_code,
    nuts2_code      = EXCLUDED.nuts2_code,
    nuts3_code      = EXCLUDED.nuts3_code;

-- dim indicateur
INSERT INTO data_mart.dim_indicator (
    indicator_code,
    indicator_name,
    source_code,
    unit,
    indicator_description,
    aggregation_rule
)
SELECT DISTINCT
    indicator_code,
    indicator_name,
    source_system,
    COALESCE(unit, 'UNKNOWN'),

    CASE
        WHEN indicator_code LIKE '%ARBEITSLOSE%'
            THEN 'Effectif de chômeurs enregistrés par BA.'
        WHEN indicator_code LIKE '%UNTERBESCHAEFTIGUNG%'
            THEN 'Effectif de personnes en sous-emploi selon BA.'
        ELSE
            'Indicateur Eurostat à interpréter selon ses dimensions statistiques.'
    END,

    CASE
        WHEN indicator_code LIKE '%_AVG'
            THEN 'AVG'
        WHEN indicator_code LIKE '%_DEC'
            THEN 'YEAR_END_SNAPSHOT'
        WHEN source_system = 'EUROSTAT'
            THEN 'NON_ADDITIVE'
        ELSE 'REVIEW_REQUIRED'
    END

FROM business_vault.vw_labour_market_indicators
ON CONFLICT (source_code, indicator_code, unit)
DO UPDATE SET
    indicator_name        = EXCLUDED.indicator_name,
    indicator_description = EXCLUDED.indicator_description,
    aggregation_rule      = EXCLUDED.aggregation_rule;

-- dim periode
-- Périodes mensuelles BA
WITH bounds AS (
    SELECT
        date_trunc('month', MIN(period))::DATE AS min_month,
        date_trunc('month', MAX(period))::DATE AS max_month
    FROM raw_vault.sat_ba_labour_market
    WHERE load_end_dts IS NULL
),
months AS (
    SELECT
        gs::DATE AS month_start
    FROM bounds b
    CROSS JOIN LATERAL generate_series(
        b.min_month::TIMESTAMP,
        b.max_month::TIMESTAMP,
        INTERVAL '1 month'
    ) AS gs
    WHERE b.min_month IS NOT NULL
)
INSERT INTO data_mart.dim_period (
    period_code,
    period_type,
    period_start_date,
    period_end_date,
    period_year,
    period_month,
    period_quarter,
    period_label
)
SELECT
    'M:' || TO_CHAR(month_start, 'YYYY-MM'),
    'MONTH',
    month_start,
    (month_start + INTERVAL '1 month - 1 day')::DATE,
    EXTRACT(YEAR FROM month_start)::INTEGER,
    EXTRACT(MONTH FROM month_start)::SMALLINT,
    EXTRACT(QUARTER FROM month_start)::SMALLINT,
    TO_CHAR(month_start, 'YYYY-MM')
FROM months
ON CONFLICT (period_code) DO NOTHING;

-- periode annuelle
WITH year_bounds AS (
    SELECT
        LEAST(
            (
                SELECT MIN(period_bk::INTEGER)
                FROM raw_vault.sat_eurostat_unemployment
                WHERE load_end_dts IS NULL
            ),
            (
                SELECT MIN(EXTRACT(YEAR FROM period)::INTEGER)
                FROM raw_vault.sat_ba_labour_market
                WHERE load_end_dts IS NULL
            )
        ) AS min_year,

        GREATEST(
            (
                SELECT MAX(period_bk::INTEGER)
                FROM raw_vault.sat_eurostat_unemployment
                WHERE load_end_dts IS NULL
            ),
            (
                SELECT MAX(EXTRACT(YEAR FROM period)::INTEGER)
                FROM raw_vault.sat_ba_labour_market
                WHERE load_end_dts IS NULL
            )
        ) AS max_year
),
years AS (
    SELECT GENERATE_SERIES(min_year, max_year) AS year_num
    FROM year_bounds
    WHERE min_year IS NOT NULL
      AND max_year IS NOT NULL
)
INSERT INTO data_mart.dim_period (
    period_code,
    period_type,
    period_start_date,
    period_end_date,
    period_year,
    period_month,
    period_quarter,
    period_label
)
SELECT
    'Y:' || year_num,
    'YEAR',
    MAKE_DATE(year_num, 1, 1),
    MAKE_DATE(year_num, 12, 31),
    year_num,
    NULL,
    NULL,
    year_num::VARCHAR
FROM years
ON CONFLICT (period_code) DO NOTHING;

-- controle
SELECT 'dim_geography' AS dimension, COUNT(*) AS lignes
FROM data_mart.dim_geography

UNION ALL

SELECT 'dim_period', COUNT(*)
FROM data_mart.dim_period

UNION ALL

SELECT 'dim_indicator', COUNT(*)
FROM data_mart.dim_indicator

UNION ALL

SELECT 'dim_source', COUNT(*)
FROM data_mart.dim_source;

-- controle
SELECT
    geography_system,
    geography_level,
    COUNT(*) AS nombre_geographies
FROM data_mart.dim_geography
GROUP BY geography_system, geography_level
ORDER BY geography_system, geography_level;