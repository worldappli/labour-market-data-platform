CREATE OR REPLACE VIEW business_vault.vw_ba_annual_indicators AS

WITH monthly_data AS (
    SELECT
        s.geography_hk,
        s.period,
        EXTRACT(YEAR FROM s.period)::INTEGER AS year_num,
        EXTRACT(MONTH FROM s.period)::INTEGER AS month_num,
        s.arbeitslose,
        s.unterbeschaeftigung
    FROM raw_vault.sat_ba_labour_market AS s
    WHERE s.load_end_dts IS NULL
),

annual_aggregation AS (
    SELECT
        geography_hk,
        year_num,

        -- Couverture temporelle
        COUNT(DISTINCT period) AS months_available,

        COUNT(*) FILTER (
            WHERE arbeitslose IS NOT NULL
        ) AS arbeitslose_months_available,

        COUNT(*) FILTER (
            WHERE unterbeschaeftigung IS NOT NULL
        ) AS unterbeschaeftigung_months_available,

        -- Moyenne des effectifs mensuels
        AVG(arbeitslose) AS arbeitslose_avg_raw,
        AVG(unterbeschaeftigung) AS unterbeschaeftigung_avg_raw,

        -- Valeurs du mois de décembre
        MAX(arbeitslose) FILTER (
            WHERE month_num = 12
        ) AS arbeitslose_december,

        MAX(unterbeschaeftigung) FILTER (
            WHERE month_num = 12
        ) AS unterbeschaeftigung_december

    FROM monthly_data
    GROUP BY geography_hk, year_num
)

SELECT
    -- Identité géographique
    g.ags,
    h.kreis,
    h.nuts3_code,
    h.nuts2_code,
    h.nuts1_code,

    -- Année
    a.year_num AS year,

    -- Couverture temporelle
    a.months_available,
    a.arbeitslose_months_available,
    a.unterbeschaeftigung_months_available,

    -- Moyennes annuelles : uniquement avec 12 mois valides
    CASE
        WHEN a.arbeitslose_months_available = 12
        THEN ROUND(a.arbeitslose_avg_raw, 2)
        ELSE NULL
    END AS arbeitslose_annual_avg,

    CASE
        WHEN a.unterbeschaeftigung_months_available = 12
        THEN ROUND(a.unterbeschaeftigung_avg_raw, 2)
        ELSE NULL
    END AS unterbeschaeftigung_annual_avg,

    -- Effectifs en décembre : photographie de fin d'année
    a.arbeitslose_december,
    a.unterbeschaeftigung_december,

    -- Indicateurs de complétude
    (a.arbeitslose_months_available = 12)
        AS arbeitslose_year_complete,

    (a.unterbeschaeftigung_months_available = 12)
        AS unterbeschaeftigung_year_complete

FROM annual_aggregation AS a

JOIN raw_vault.hub_geography AS g
    ON g.geography_hk = a.geography_hk

LEFT JOIN business_vault.vw_ba_geography_hierarchy AS h
    ON h.ags = g.ags;

-- Controle de la view
SELECT *
FROM business_vault.vw_ba_annual_indicators
ORDER BY ags, year
LIMIT 30;

-- couverture de l'annee
SELECT
    year,
    COUNT(*) AS territoires,

    COUNT(*) FILTER (
        WHERE arbeitslose_year_complete
    ) AS territoires_annee_complete_arbeitslose,

    COUNT(*) FILTER (
        WHERE unterbeschaeftigung_year_complete
    ) AS territoires_annee_complete_unterbeschaeftigung,

    COUNT(*) FILTER (
        WHERE months_available < 12
    ) AS territoires_avec_annee_incomplete

FROM business_vault.vw_ba_annual_indicators
GROUP BY year
ORDER BY year;

-- verification de doublons
SELECT
    ags,
    year,
    COUNT(*) AS nombre_lignes
FROM business_vault.vw_ba_annual_indicators
GROUP BY ags, year
HAVING COUNT(*) > 1;


----------------------------------------------------
-- Creation de la views vw_labour_indicateurs
----------------------------------------------------
CREATE OR REPLACE VIEW business_vault.vw_labour_market_indicators AS

WITH

-- ============================================================
-- 1. INDICATEURS ANNUELS BA
-- ============================================================

ba_indicators AS (
    SELECT
        b.ags AS geography_code,
        b.kreis AS geography_name,
        'KREIS'::VARCHAR AS geography_level,

        b.nuts1_code,
        b.nuts2_code,
        b.nuts3_code,

        b.year::INTEGER AS period_year,
        'ANNUAL'::VARCHAR AS period_type,

        'BA'::VARCHAR AS source_system,
        v.indicator_code,
        v.indicator_name,
        v.indicator_value::NUMERIC AS indicator_value,
        'PERSONS'::VARCHAR AS unit,

        NULL::VARCHAR AS freq,
        NULL::VARCHAR AS isced11,
        NULL::VARCHAR AS sex,
        NULL::VARCHAR AS age,
        NULL::VARCHAR AS status

    FROM business_vault.vw_ba_annual_indicators AS b

    CROSS JOIN LATERAL (
        VALUES
        (
            'BA_ARBEITSLOSE_AVG'::VARCHAR,
            'Registered unemployed - annual average'::VARCHAR,
            b.arbeitslose_annual_avg::NUMERIC
        ),
        (
            'BA_UNTERBESCHAEFTIGUNG_AVG'::VARCHAR,
            'Underemployment - annual average'::VARCHAR,
            b.unterbeschaeftigung_annual_avg::NUMERIC
        )
    ) AS v(
        indicator_code,
        indicator_name,
        indicator_value
    )

    WHERE v.indicator_value IS NOT NULL
),

-- ============================================================
-- 2. INDICATEURS BA DU MOIS DE DECEMBRE
-- ============================================================

ba_december AS (
    SELECT
        b.ags AS geography_code,
        b.kreis AS geography_name,
        'KREIS'::VARCHAR AS geography_level,

        b.nuts1_code,
        b.nuts2_code,
        b.nuts3_code,

        b.year::INTEGER AS period_year,
        'DECEMBER'::VARCHAR AS period_type,

        'BA'::VARCHAR AS source_system,
        v.indicator_code,
        v.indicator_name,
        v.indicator_value::NUMERIC AS indicator_value,
        'PERSONS'::VARCHAR AS unit,

        NULL::VARCHAR AS freq,
        NULL::VARCHAR AS isced11,
        NULL::VARCHAR AS sex,
        NULL::VARCHAR AS age,
        NULL::VARCHAR AS status

    FROM business_vault.vw_ba_annual_indicators AS b

    CROSS JOIN LATERAL (
        VALUES
        (
            'BA_ARBEITSLOSE_DEC'::VARCHAR,
            'Registered unemployed - December'::VARCHAR,
            b.arbeitslose_december::NUMERIC
        ),
        (
            'BA_UNTERBESCHAEFTIGUNG_DEC'::VARCHAR,
            'Underemployment - December'::VARCHAR,
            b.unterbeschaeftigung_december::NUMERIC
        )
    ) AS v(
        indicator_code,
        indicator_name,
        indicator_value
    )

    WHERE v.indicator_value IS NOT NULL
),

-- ============================================================
-- 3. INDICATEURS EUROSTAT
-- ============================================================

eurostat_indicators AS (
    SELECT
        g.geo_code AS geography_code,
        COALESCE(geo.region, g.geo_code) AS geography_name,

        CASE
            WHEN g.geo_code = 'DE' THEN 'COUNTRY'
            WHEN sn.nuts_level = 1 THEN 'NUTS1'
            WHEN sn.nuts_level = 2 THEN 'NUTS2'
            WHEN sn.nuts_level = 3 THEN 'NUTS3'
            ELSE 'UNKNOWN'
        END::VARCHAR AS geography_level,

        CASE
            WHEN sn.nuts_level = 1 THEN n.nuts_code
            WHEN sn.nuts_level = 2 THEN parent_n1.nuts_code
            WHEN sn.nuts_level = 3 THEN parent_n2.nuts_code
            ELSE NULL
        END::VARCHAR AS nuts1_code,

        CASE
            WHEN sn.nuts_level = 2 THEN n.nuts_code
            WHEN sn.nuts_level = 3 THEN parent_n2.nuts_code
            ELSE NULL
        END::VARCHAR AS nuts2_code,

        CASE
            WHEN sn.nuts_level = 3 THEN n.nuts_code
            ELSE NULL
        END::VARCHAR AS nuts3_code,

        NULLIF(u.period_bk, '')::INTEGER AS period_year,
        'ANNUAL'::VARCHAR AS period_type,

        'EUROSTAT'::VARCHAR AS source_system,
        'EUROSTAT_UNEMPLOYMENT_RATE'::VARCHAR AS indicator_code,
        'Unemployment rate by statistical dimensions'::VARCHAR
            AS indicator_name,

        u.value::NUMERIC AS indicator_value,
        ser.unit::VARCHAR AS unit,

        ser.freq::VARCHAR AS freq,
        ser.isced11::VARCHAR AS isced11,
        ser.sex::VARCHAR AS sex,
        ser.age::VARCHAR AS age,
        u.status::VARCHAR AS status

    FROM raw_vault.sat_eurostat_unemployment AS u

    JOIN raw_vault.link_eurostat_geo_series AS lgs
        ON lgs.eurostat_geo_series_hk = u.eurostat_geo_series_hk

    JOIN raw_vault.hub_eurostat_geo AS g
        ON g.eurostat_geo_hk = lgs.eurostat_geo_hk

    JOIN raw_vault.hub_eurostat_series AS hs
        ON hs.eurostat_series_hk = lgs.eurostat_series_hk

    JOIN raw_vault.sat_eurostat_series AS ser
        ON ser.eurostat_series_hk = hs.eurostat_series_hk
       AND ser.load_end_dts IS NULL

    LEFT JOIN raw_vault.sat_eurostat_geo AS geo
        ON geo.eurostat_geo_hk = g.eurostat_geo_hk
       AND geo.load_end_dts IS NULL

    -- Code géographique Eurostat -> Hub NUTS
    LEFT JOIN raw_vault.hub_nuts AS n
        ON n.nuts_code = g.geo_code

    -- CORRECTION : nuts_level se trouve dans sat_nuts
    LEFT JOIN raw_vault.sat_nuts AS sn
        ON sn.nuts_hk = n.nuts_hk
       AND sn.load_end_dts IS NULL

    -- Hiérarchie géographique
    LEFT JOIN raw_vault.link_nuts_hierarchy AS hierarchy
        ON hierarchy.child_nuts_hk = n.nuts_hk

    LEFT JOIN raw_vault.hub_nuts AS parent_n1
        ON parent_n1.nuts_hk = hierarchy.parent_nuts_hk
       AND sn.nuts_level = 2

    LEFT JOIN raw_vault.hub_nuts AS parent_n2
        ON parent_n2.nuts_hk = hierarchy.parent_nuts_hk
       AND sn.nuts_level = 3

    WHERE u.load_end_dts IS NULL
)

-- ============================================================
-- 4. UNION DES INDICATEURS
-- ============================================================

SELECT * FROM ba_indicators

UNION ALL

SELECT * FROM ba_december

UNION ALL

SELECT * FROM eurostat_indicators;

--COntrole
SELECT
    source_system,
    indicator_code,
    unit,
    period_type,
    COUNT(*) AS observations,
    MIN(period_year) AS premiere_annee,
    MAX(period_year) AS derniere_annee
FROM business_vault.vw_labour_market_indicators
GROUP BY
    source_system,
    indicator_code,
    unit,
    period_type
ORDER BY
    source_system,
    indicator_code;

 -- classification
 SELECT
    geography_level,
    COUNT(DISTINCT geography_code) AS geographies,
    COUNT(*) AS observations
FROM business_vault.vw_labour_market_indicators
WHERE source_system = 'EUROSTAT'
GROUP BY geography_level
ORDER BY geography_level;