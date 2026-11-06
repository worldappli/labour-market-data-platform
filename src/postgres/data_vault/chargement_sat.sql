
BEGIN;

-- ============================================================
-- 0. SÉCURISATION DU BATCH
-- ============================================================

SELECT pg_advisory_xact_lock(
    hashtext('raw_vault.satellite_load')::BIGINT
);

CREATE TEMP TABLE _dv_batch ON COMMIT DROP AS
SELECT transaction_timestamp() AS batch_dts;


-- ============================================================
-- 1. FONCTION HASHDIFF
-- ============================================================

-- Gère les valeurs NULL et distingue NULL de chaîne vide.
-- L'ordre des attributs doit rester identique à chaque chargement.

CREATE OR REPLACE FUNCTION raw_vault.sha256_hashdiff(
    VARIADIC p_values TEXT[]
)
RETURNS CHAR(64)
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT encode(
        digest(
            convert_to(
                jsonb_build_array(VARIADIC p_values)::TEXT,
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )::CHAR(64);
$$;


-- ============================================================
-- 2. CONTRÔLES DES SOURCES
-- ============================================================

-- BA : pas de mesures contradictoires au grain AGS + période.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM staging.ba_arbeitslosigkeit
        WHERE ags IS NOT NULL AND period IS NOT NULL
        GROUP BY
            TRIM(ags),
            CASE
                WHEN period::TEXT ~ '^[0-9]{4}-[0-9]{2}$'
                    THEN TO_DATE(period::TEXT || '-01', 'YYYY-MM-DD')
                ELSE period::DATE
            END
        HAVING COUNT(DISTINCT
            jsonb_build_array(arbeitslose, unterbeschaeftigung)
        ) > 1
    ) THEN
        RAISE EXCEPTION
            'BA : mesures contradictoires pour un même AGS + période.';
    END IF;
END $$;

-- BA : les attributs descriptifs doivent être cohérents par AGS.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM staging.ba_arbeitslosigkeit
        WHERE ags IS NOT NULL
        GROUP BY TRIM(ags)
        HAVING COUNT(DISTINCT
            jsonb_build_array(ba_id, TRIM(kreis))
        ) > 1
    ) THEN
        RAISE EXCEPTION
            'BA : attributs descriptifs contradictoires pour un AGS.';
    END IF;
END $$;

-- Eurostat : pas de valeurs contradictoires au grain complet.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM staging.eurostat_unemployment
        WHERE geo IS NOT NULL AND time IS NOT NULL
        GROUP BY
            UPPER(TRIM(geo)),
            time,
            TRIM(freq),
            TRIM(isced11),
            TRIM(sex),
            TRIM(age),
            TRIM(unit)
        HAVING COUNT(DISTINCT
            jsonb_build_array(value, NULLIF(TRIM(status), ''))
        ) > 1
    ) THEN
        RAISE EXCEPTION
            'Eurostat : valeurs contradictoires pour une observation.';
    END IF;
END $$;

-- Eurostat : un seul libellé non vide par code géographique.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM staging.eurostat_unemployment
        WHERE geo IS NOT NULL
          AND NULLIF(TRIM(region), '') IS NOT NULL
        GROUP BY UPPER(TRIM(geo))
        HAVING COUNT(DISTINCT TRIM(region)) > 1
    ) THEN
        RAISE EXCEPTION
            'Eurostat : plusieurs libellés pour une même géographie.';
    END IF;
END $$;


-- ============================================================
-- 3. PRÉPARATION DES SEPT SATELLITES
-- ============================================================

-- 3.1 SAT_GEOGRAPHY_BA
CREATE TEMP TABLE _in_sat_geography_ba ON COMMIT DROP AS
SELECT DISTINCT
    h.geography_hk,
    b.ba_id,
    TRIM(b.kreis) AS kreis,
    raw_vault.sha256_hashdiff(
        b.ba_id,
        TRIM(b.kreis)
    ) AS hashdiff,
    'BA'::VARCHAR(100) AS record_source
FROM staging.ba_arbeitslosigkeit b
JOIN raw_vault.hub_geography h
    ON h.ags = TRIM(b.ags)
WHERE b.ags IS NOT NULL
  AND b.kreis IS NOT NULL;


-- 3.2 SAT_NUTS
CREATE TEMP TABLE _in_sat_nuts ON COMMIT DROP AS
SELECT DISTINCT
    h.nuts_hk,
    n.nuts_level,
    n.country_code,
    n.reference_year,
    raw_vault.sha256_hashdiff(
        n.nuts_level::TEXT,
        n.country_code,
        n.reference_year::TEXT
    ) AS hashdiff,
    n.source_system::VARCHAR(100) AS record_source
FROM staging.nuts_reference n
JOIN raw_vault.hub_nuts h
    ON h.nuts_code = UPPER(TRIM(n.nuts_code));


-- 3.3 SAT_GEOGRAPHY_NUTS_MAPPING
CREATE TEMP TABLE _in_sat_geography_nuts_mapping
ON COMMIT DROP AS
SELECT DISTINCT
    l.geography_nuts_hk,
    m.mapping_method,
    m.mapping_status,
    m.mapping_source,
    raw_vault.sha256_hashdiff(
        m.mapping_method,
        m.mapping_status,
        m.mapping_source
    ) AS hashdiff,
    'AGS_NUTS_MAPPING'::VARCHAR(100) AS record_source
FROM staging.ags_nuts_mapping m
JOIN raw_vault.hub_geography g
    ON g.ags = TRIM(m.ags)
JOIN raw_vault.hub_nuts n
    ON n.nuts_code = UPPER(TRIM(m.nuts3_code))
JOIN raw_vault.link_geography_nuts l
    ON l.geography_hk = g.geography_hk
   AND l.nuts_hk = n.nuts_hk
WHERE m.nuts3_code IS NOT NULL;


-- 3.4 SAT_BA_LABOUR_MARKET
CREATE TEMP TABLE _in_sat_ba_labour_market
ON COMMIT DROP AS
SELECT DISTINCT
    h.geography_hk,
    CASE
        WHEN b.period::TEXT ~ '^[0-9]{4}-[0-9]{2}$'
            THEN TO_DATE(b.period::TEXT || '-01', 'YYYY-MM-DD')
        ELSE b.period::DATE
    END AS period,
    b.arbeitslose::BIGINT AS arbeitslose,
    b.unterbeschaeftigung::BIGINT AS unterbeschaeftigung,
    raw_vault.sha256_hashdiff(
        b.arbeitslose::TEXT,
        b.unterbeschaeftigung::TEXT
    ) AS hashdiff,
    'BA'::VARCHAR(100) AS record_source
FROM staging.ba_arbeitslosigkeit b
JOIN raw_vault.hub_geography h
    ON h.ags = TRIM(b.ags)
WHERE b.ags IS NOT NULL
  AND b.period IS NOT NULL;


-- 3.5 SAT_EUROSTAT_GEO
-- Agrégation pour obtenir exactement un libellé par geo.
CREATE TEMP TABLE _in_sat_eurostat_geo
ON COMMIT DROP AS
SELECT
    h.eurostat_geo_hk,
    MAX(NULLIF(TRIM(e.region), '')) AS region,
    raw_vault.sha256_hashdiff(
        MAX(NULLIF(TRIM(e.region), ''))
    ) AS hashdiff,
    'EUROSTAT'::VARCHAR(100) AS record_source
FROM staging.eurostat_unemployment e
JOIN raw_vault.hub_eurostat_geo h
    ON h.geo_code = UPPER(TRIM(e.geo))
GROUP BY h.eurostat_geo_hk;


-- 3.6 SAT_EUROSTAT_SERIES
CREATE TEMP TABLE _in_sat_eurostat_series
ON COMMIT DROP AS
SELECT DISTINCT
    h.eurostat_series_hk,
    TRIM(e.freq) AS freq,
    TRIM(e.isced11) AS isced11,
    TRIM(e.sex) AS sex,
    TRIM(e.age) AS age,
    TRIM(e.unit) AS unit,
    raw_vault.sha256_hashdiff(
        TRIM(e.freq),
        TRIM(e.isced11),
        TRIM(e.sex),
        TRIM(e.age),
        TRIM(e.unit)
    ) AS hashdiff,
    'EUROSTAT'::VARCHAR(100) AS record_source
FROM staging.eurostat_unemployment e
JOIN raw_vault.hub_eurostat_series h
    ON h.series_bk = jsonb_build_array(
        TRIM(e.freq),
        TRIM(e.isced11),
        TRIM(e.sex),
        TRIM(e.age),
        TRIM(e.unit)
    )::TEXT;


-- 3.7 SAT_EUROSTAT_UNEMPLOYMENT
CREATE TEMP TABLE _in_sat_eurostat_unemployment
ON COMMIT DROP AS
SELECT DISTINCT
    l.eurostat_geo_series_hk,
    e.time::TEXT AS period_bk,
    e.value::NUMERIC(10,2) AS value,
    NULLIF(TRIM(e.status), '') AS status,
    raw_vault.sha256_hashdiff(
        e.value::NUMERIC(10,2)::TEXT,
        NULLIF(TRIM(e.status), '')
    ) AS hashdiff,
    'EUROSTAT'::VARCHAR(100) AS record_source
FROM staging.eurostat_unemployment e
JOIN raw_vault.hub_eurostat_geo hg
    ON hg.geo_code = UPPER(TRIM(e.geo))
JOIN raw_vault.hub_eurostat_series hs
    ON hs.series_bk = jsonb_build_array(
        TRIM(e.freq),
        TRIM(e.isced11),
        TRIM(e.sex),
        TRIM(e.age),
        TRIM(e.unit)
    )::TEXT
JOIN raw_vault.link_eurostat_geo_series l
    ON l.eurostat_geo_hk = hg.eurostat_geo_hk
   AND l.eurostat_series_hk = hs.eurostat_series_hk
WHERE e.time IS NOT NULL
  AND e.value IS NOT NULL;


-- ============================================================
-- 4. CONTRÔLE DE L'UNICITÉ DES GRAINS
-- ============================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM _in_sat_geography_ba
        GROUP BY geography_hk HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_geography_ba';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_nuts
        GROUP BY nuts_hk HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_nuts';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_geography_nuts_mapping
        GROUP BY geography_nuts_hk HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_geography_nuts_mapping';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_ba_labour_market
        GROUP BY geography_hk, period HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_ba_labour_market';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_eurostat_geo
        GROUP BY eurostat_geo_hk HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_eurostat_geo';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_eurostat_series
        GROUP BY eurostat_series_hk HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_eurostat_series';
    END IF;

    IF EXISTS (
        SELECT 1 FROM _in_sat_eurostat_unemployment
        GROUP BY eurostat_geo_series_hk, period_bk
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Grain non unique : sat_eurostat_unemployment';
    END IF;
END $$;


-- ============================================================
-- 5. HISTORISATION : SAT_GEOGRAPHY_BA
-- ============================================================

UPDATE raw_vault.sat_geography_ba old
SET load_end_dts = b.batch_dts
FROM _in_sat_geography_ba inc
CROSS JOIN _dv_batch b
WHERE old.geography_hk = inc.geography_hk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_geography_ba (
    geography_hk, load_dts, load_end_dts,
    hashdiff, ba_id, kreis, record_source
)
SELECT
    inc.geography_hk, b.batch_dts, NULL,
    inc.hashdiff, inc.ba_id, inc.kreis, inc.record_source
FROM _in_sat_geography_ba inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_geography_ba old
    WHERE old.geography_hk = inc.geography_hk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 6. HISTORISATION : SAT_NUTS
-- ============================================================

UPDATE raw_vault.sat_nuts old
SET load_end_dts = b.batch_dts
FROM _in_sat_nuts inc
CROSS JOIN _dv_batch b
WHERE old.nuts_hk = inc.nuts_hk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_nuts (
    nuts_hk, load_dts, load_end_dts, hashdiff,
    nuts_level, country_code, reference_year, record_source
)
SELECT
    inc.nuts_hk, b.batch_dts, NULL, inc.hashdiff,
    inc.nuts_level, inc.country_code,
    inc.reference_year, inc.record_source
FROM _in_sat_nuts inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_nuts old
    WHERE old.nuts_hk = inc.nuts_hk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 7. HISTORISATION : SAT_GEOGRAPHY_NUTS_MAPPING
-- ============================================================

UPDATE raw_vault.sat_geography_nuts_mapping old
SET load_end_dts = b.batch_dts
FROM _in_sat_geography_nuts_mapping inc
CROSS JOIN _dv_batch b
WHERE old.geography_nuts_hk = inc.geography_nuts_hk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_geography_nuts_mapping (
    geography_nuts_hk, load_dts, load_end_dts, hashdiff,
    mapping_method, mapping_status, mapping_source, record_source
)
SELECT
    inc.geography_nuts_hk, b.batch_dts, NULL, inc.hashdiff,
    inc.mapping_method, inc.mapping_status,
    inc.mapping_source, inc.record_source
FROM _in_sat_geography_nuts_mapping inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_geography_nuts_mapping old
    WHERE old.geography_nuts_hk = inc.geography_nuts_hk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 8. HISTORISATION : SAT_BA_LABOUR_MARKET
-- ============================================================

UPDATE raw_vault.sat_ba_labour_market old
SET load_end_dts = b.batch_dts
FROM _in_sat_ba_labour_market inc
CROSS JOIN _dv_batch b
WHERE old.geography_hk = inc.geography_hk
  AND old.period = inc.period
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_ba_labour_market (
    geography_hk, period, load_dts, load_end_dts,
    hashdiff, arbeitslose, unterbeschaeftigung, record_source
)
SELECT
    inc.geography_hk, inc.period, b.batch_dts, NULL,
    inc.hashdiff, inc.arbeitslose,
    inc.unterbeschaeftigung, inc.record_source
FROM _in_sat_ba_labour_market inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_ba_labour_market old
    WHERE old.geography_hk = inc.geography_hk
      AND old.period = inc.period
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 9. HISTORISATION : SAT_EUROSTAT_GEO
-- ============================================================

UPDATE raw_vault.sat_eurostat_geo old
SET load_end_dts = b.batch_dts
FROM _in_sat_eurostat_geo inc
CROSS JOIN _dv_batch b
WHERE old.eurostat_geo_hk = inc.eurostat_geo_hk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_eurostat_geo (
    eurostat_geo_hk, load_dts, load_end_dts,
    hashdiff, region, record_source
)
SELECT
    inc.eurostat_geo_hk, b.batch_dts, NULL,
    inc.hashdiff, inc.region, inc.record_source
FROM _in_sat_eurostat_geo inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_eurostat_geo old
    WHERE old.eurostat_geo_hk = inc.eurostat_geo_hk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 10. HISTORISATION : SAT_EUROSTAT_SERIES
-- ============================================================

UPDATE raw_vault.sat_eurostat_series old
SET load_end_dts = b.batch_dts
FROM _in_sat_eurostat_series inc
CROSS JOIN _dv_batch b
WHERE old.eurostat_series_hk = inc.eurostat_series_hk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_eurostat_series (
    eurostat_series_hk, load_dts, load_end_dts,
    hashdiff, freq, isced11, sex, age, unit, record_source
)
SELECT
    inc.eurostat_series_hk, b.batch_dts, NULL,
    inc.hashdiff, inc.freq, inc.isced11,
    inc.sex, inc.age, inc.unit, inc.record_source
FROM _in_sat_eurostat_series inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_eurostat_series old
    WHERE old.eurostat_series_hk = inc.eurostat_series_hk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 11. HISTORISATION : SAT_EUROSTAT_UNEMPLOYMENT
-- ============================================================

UPDATE raw_vault.sat_eurostat_unemployment old
SET load_end_dts = b.batch_dts
FROM _in_sat_eurostat_unemployment inc
CROSS JOIN _dv_batch b
WHERE old.eurostat_geo_series_hk = inc.eurostat_geo_series_hk
  AND old.period_bk = inc.period_bk
  AND old.load_end_dts IS NULL
  AND old.hashdiff <> inc.hashdiff;

INSERT INTO raw_vault.sat_eurostat_unemployment (
    eurostat_geo_series_hk, period_bk, load_dts, load_end_dts,
    hashdiff, value, status, record_source
)
SELECT
    inc.eurostat_geo_series_hk, inc.period_bk,
    b.batch_dts, NULL, inc.hashdiff,
    inc.value, inc.status, inc.record_source
FROM _in_sat_eurostat_unemployment inc
CROSS JOIN _dv_batch b
WHERE NOT EXISTS (
    SELECT 1
    FROM raw_vault.sat_eurostat_unemployment old
    WHERE old.eurostat_geo_series_hk = inc.eurostat_geo_series_hk
      AND old.period_bk = inc.period_bk
      AND old.load_end_dts IS NULL
      AND old.hashdiff = inc.hashdiff
);


-- ============================================================
-- 12. CONTRÔLES FINAUX
-- ============================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM raw_vault.sat_ba_labour_market
        WHERE load_end_dts IS NOT NULL
          AND load_end_dts <= load_dts
    ) THEN
        RAISE EXCEPTION
            'Dates invalides dans sat_ba_labour_market';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw_vault.sat_eurostat_unemployment
        WHERE load_end_dts IS NOT NULL
          AND load_end_dts <= load_dts
    ) THEN
        RAISE EXCEPTION
            'Dates invalides dans sat_eurostat_unemployment';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw_vault.sat_ba_labour_market
        WHERE load_end_dts IS NULL
        GROUP BY geography_hk, period
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Plusieurs versions courantes pour un AGS + période';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw_vault.sat_eurostat_unemployment
        WHERE load_end_dts IS NULL
        GROUP BY eurostat_geo_series_hk, period_bk
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Plusieurs versions courantes pour une observation Eurostat';
    END IF;
END $$;

COMMIT;

-- controle

SELECT 'sat_geography_ba' AS satellite,
       COUNT(*) AS total_versions,
       COUNT(*) FILTER (WHERE load_end_dts IS NULL) AS current_versions
FROM raw_vault.sat_geography_ba

UNION ALL
SELECT 'sat_nuts', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_nuts

UNION ALL
SELECT 'sat_geography_nuts_mapping', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_geography_nuts_mapping

UNION ALL
SELECT 'sat_ba_labour_market', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_ba_labour_market

UNION ALL
SELECT 'sat_eurostat_geo', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_eurostat_geo

UNION ALL
SELECT 'sat_eurostat_series', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_eurostat_series

UNION ALL
SELECT 'sat_eurostat_unemployment', COUNT(*),
       COUNT(*) FILTER (WHERE load_end_dts IS NULL)
FROM raw_vault.sat_eurostat_unemployment

ORDER BY satellite;
