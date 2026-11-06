CREATE OR REPLACE VIEW data_mart.vw_superset_ba_monthly AS
SELECT
    f.fact_key,
    dg.geography_code,
    dg.geography_name,
    dg.ags,
    dg.nuts1_code,
    dg.nuts2_code,
    dg.nuts3_code,

    dp.period_start_date AS observation_date,
    dp.period_year AS year,
    dp.period_month AS month,
    dp.period_label,

    di.indicator_code,
    di.indicator_name,
    di.unit,

    f.indicator_value,
    f.observation_status,
    f.loaded_at

FROM data_mart.fact_labour_market AS f

JOIN data_mart.dim_geography AS dg
    ON dg.geography_key = f.geography_key

JOIN data_mart.dim_period AS dp
    ON dp.period_key = f.period_key

JOIN data_mart.dim_indicator AS di
    ON di.indicator_key = f.indicator_key

JOIN data_mart.dim_source AS ds
    ON ds.source_key = f.source_key

WHERE ds.source_code = 'BA'
  AND di.indicator_code IN (
      'BA_ARBEITSLOSE_MONTHLY',
      'BA_UNTERBESCHAEFTIGUNG_MONTHLY'
  )
  AND dp.period_type = 'MONTH';

 -- controle
 SELECT
    indicator_code,
    COUNT(*) AS observations,
    MIN(observation_date) AS premiere_date,
    MAX(observation_date) AS derniere_date,
    COUNT(DISTINCT geography_code) AS territoires
FROM data_mart.vw_superset_ba_monthly
GROUP BY indicator_code
ORDER BY indicator_code;

-- vues des indicateur annuel
CREATE OR REPLACE VIEW data_mart.vw_superset_annual_indicators AS
SELECT
    f.fact_key,

    ds.source_code,
    ds.source_name,

    dg.geography_system,
    dg.geography_code,
    dg.geography_name,
    dg.geography_level,
    dg.ags,
    dg.nuts1_code,
    dg.nuts2_code,
    dg.nuts3_code,

    dp.period_year AS year,
    dp.period_type AS dimension_period_type,
    dp.period_start_date,
    dp.period_end_date,

    di.indicator_code,
    di.indicator_name,
    di.unit,
    di.aggregation_rule,

    f.indicator_value,
    f.freq,
    f.isced11,
    f.sex,
    f.age,
    f.observation_status,
    f.months_available,
    f.is_complete

FROM data_mart.fact_labour_market AS f

JOIN data_mart.dim_source AS ds
    ON ds.source_key = f.source_key

JOIN data_mart.dim_geography AS dg
    ON dg.geography_key = f.geography_key

JOIN data_mart.dim_period AS dp
    ON dp.period_key = f.period_key

JOIN data_mart.dim_indicator AS di
    ON di.indicator_key = f.indicator_key

WHERE
    di.indicator_code IN (
        'BA_ARBEITSLOSE_AVG',
        'BA_UNTERBESCHAEFTIGUNG_AVG',
        'BA_ARBEITSLOSE_DEC',
        'BA_UNTERBESCHAEFTIGUNG_DEC'
    )
    OR ds.source_code = 'EUROSTAT';

-- view superset geography map
CREATE OR REPLACE VIEW data_mart.vw_superset_geography_map AS
SELECT
    ags_kreis,
    ags_ba_candidate,
    kreis_name,
    kreis_type,
    bundesland_code,
    reference_date,
    geojson_feature,
    1::INTEGER AS territoire_count
FROM data_mart.geo_kreis;

-- controle
SELECT
    source_code,
    indicator_code,
    unit,
    year,
    COUNT(*) AS observations
FROM data_mart.vw_superset_annual_indicators
GROUP BY source_code, indicator_code, unit, year
ORDER BY year, source_code, indicator_code;

-- vues de consommation geographique
CREATE OR REPLACE VIEW data_mart.vw_superset_geography AS
SELECT
    geography_key,
    geography_system,
    geography_code,
    geography_name,
    geography_level,
    ags,
    nuts1_code,
    nuts2_code,
    nuts3_code
FROM data_mart.dim_geography;

-- controle
SELECT
    geography_system,
    geography_level,
    COUNT(*) AS nombre_geographies
FROM data_mart.vw_superset_geography
GROUP BY geography_system, geography_level
ORDER BY geography_system, geography_level;

-- verification view map
SELECT
    COUNT(*) AS territoires,
    COUNT(DISTINCT ags_kreis) AS ags_uniques,
    COUNT(*) FILTER (
        WHERE geojson_feature IS NULL OR geojson_feature = ''
    ) AS geojson_manquants
FROM data_mart.vw_superset_geography_map;