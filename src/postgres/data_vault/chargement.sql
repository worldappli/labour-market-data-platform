-- HUB GEOPGRAPHY
INSERT INTO raw_vault.hub_geography (
    geography_hk,
    ags,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(TRIM(ags)),
    TRIM(ags),
    'BA'
FROM staging.ba_arbeitslosigkeit
WHERE ags IS NOT NULL
  AND TRIM(ags) <> ''
ON CONFLICT (ags) DO NOTHING;

-- HUB NUTS
INSERT INTO raw_vault.hub_nuts (
    nuts_hk,
    nuts_code,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(UPPER(TRIM(nuts_code))),
    UPPER(TRIM(nuts_code)),
    'EUROSTAT_NUTS'
FROM staging.nuts_reference
WHERE nuts_code IS NOT NULL
  AND TRIM(nuts_code) <> ''
ON CONFLICT (nuts_code) DO NOTHING;

-- HUB EUROSTAT GEO
INSERT INTO raw_vault.hub_eurostat_geo (
    eurostat_geo_hk,
    geo_code,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(UPPER(TRIM(geo))),
    UPPER(TRIM(geo)),
    'EUROSTAT'
FROM staging.eurostat_unemployment
WHERE geo IS NOT NULL
  AND TRIM(geo) <> ''
ON CONFLICT (geo_code) DO NOTHING;

-- HUB EUROSTAT SERIES
INSERT INTO raw_vault.hub_eurostat_series (
    eurostat_series_hk,
    series_bk,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(
        TRIM(freq),
        TRIM(isced11),
        TRIM(sex),
        TRIM(age),
        TRIM(unit)
    ),
    jsonb_build_array(
        TRIM(freq),
        TRIM(isced11),
        TRIM(sex),
        TRIM(age),
        TRIM(unit)
    )::TEXT,
    'EUROSTAT'
FROM staging.eurostat_unemployment
WHERE freq IS NOT NULL
  AND isced11 IS NOT NULL
  AND sex IS NOT NULL
  AND age IS NOT NULL
  AND unit IS NOT NULL
ON CONFLICT (series_bk) DO NOTHING;

-- CONTROLE
SELECT 'hub_geography' AS table_name, COUNT(*) AS rows_count
FROM raw_vault.hub_geography

UNION ALL

SELECT 'hub_nuts', COUNT(*)
FROM raw_vault.hub_nuts

UNION ALL

SELECT 'hub_eurostat_geo', COUNT(*)
FROM raw_vault.hub_eurostat_geo

UNION ALL

SELECT 'hub_eurostat_series', COUNT(*)
FROM raw_vault.hub_eurostat_series;

----- CHARGEMENT DES LINKS -----

-- LINK GEAOGRAPHY NUTS
INSERT INTO raw_vault.link_geography_nuts (
    geography_nuts_hk,
    geography_hk,
    nuts_hk,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(
        TRIM(m.ags),
        UPPER(TRIM(m.nuts3_code))
    ),
    g.geography_hk,
    n.nuts_hk,
    COALESCE(m.mapping_source, 'AGS_NUTS_MAPPING')
FROM staging.ags_nuts_mapping m
JOIN raw_vault.hub_geography g
    ON g.ags = TRIM(m.ags)
JOIN raw_vault.hub_nuts n
    ON n.nuts_code = UPPER(TRIM(m.nuts3_code))
WHERE m.mapping_status = 'VALIDATED'
  AND m.nuts3_code IS NOT NULL
ON CONFLICT (geography_hk, nuts_hk) DO NOTHING;

-- petit control
SELECT
    COUNT(*) AS total_links,
    COUNT(DISTINCT geography_hk) AS ags_distincts,
    COUNT(DISTINCT nuts_hk) AS nuts_distincts
FROM raw_vault.link_geography_nuts;

-- LINK NUTS HIERARCHY
INSERT INTO raw_vault.link_nuts_hierarchy (
    nuts_hierarchy_hk,
    child_nuts_hk,
    parent_nuts_hk,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(
        UPPER(TRIM(child.nuts_code)),
        UPPER(TRIM(child.parent_code))
    ),
    child_hub.nuts_hk,
    parent_hub.nuts_hk,
    'EUROSTAT_NUTS'
FROM staging.nuts_reference child
JOIN raw_vault.hub_nuts child_hub
    ON child_hub.nuts_code = UPPER(TRIM(child.nuts_code))
JOIN raw_vault.hub_nuts parent_hub
    ON parent_hub.nuts_code = UPPER(TRIM(child.parent_code))
WHERE child.parent_code IS NOT NULL
  AND TRIM(child.parent_code) <> ''
ON CONFLICT (child_nuts_hk, parent_nuts_hk) DO NOTHING;

-- CONTROLE
SELECT
    child.nuts_level AS niveau_enfant,
    parent.nuts_level AS niveau_parent,
    COUNT(*) AS nombre
FROM staging.nuts_reference child
JOIN staging.nuts_reference parent
    ON parent.nuts_code = child.parent_code
GROUP BY child.nuts_level, parent.nuts_level
ORDER BY child.nuts_level;

-- LINKS EUROSTAT GEO NUTS
INSERT INTO raw_vault.link_eurostat_geo_nuts (
    eurostat_geo_nuts_hk,
    eurostat_geo_hk,
    nuts_hk,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(
        UPPER(TRIM(e.geo_code)),
        UPPER(TRIM(n.nuts_code))
    ),
    e.eurostat_geo_hk,
    n.nuts_hk,
    'EUROSTAT_GEO_NUTS_CODE_MATCH'
FROM raw_vault.hub_eurostat_geo e
JOIN raw_vault.hub_nuts n
    ON n.nuts_code = e.geo_code
ON CONFLICT (eurostat_geo_hk, nuts_hk) DO NOTHING;

-- CONTROLE
SELECT
    COUNT(*) AS total_links,
    COUNT(DISTINCT eurostat_geo_hk) AS geographies_eurostat,
    COUNT(DISTINCT nuts_hk) AS codes_nuts
FROM raw_vault.link_eurostat_geo_nuts;

-- LINK EUROSTAT GEAO SERIES
INSERT INTO raw_vault.link_eurostat_geo_series (
    eurostat_geo_series_hk,
    eurostat_geo_hk,
    eurostat_series_hk,
    record_source
)
SELECT DISTINCT
    raw_vault.sha256_key(
        UPPER(TRIM(e.geo)),
        jsonb_build_array(
            TRIM(e.freq),
            TRIM(e.isced11),
            TRIM(e.sex),
            TRIM(e.age),
            TRIM(e.unit)
        )::TEXT
    ),
    hg.eurostat_geo_hk,
    hs.eurostat_series_hk,
    'EUROSTAT'
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
ON CONFLICT (eurostat_geo_hk, eurostat_series_hk) DO NOTHING;

-- CONTROLE
SELECT
    COUNT(*) AS total_links,
    COUNT(DISTINCT eurostat_geo_hk) AS geographies,
    COUNT(DISTINCT eurostat_series_hk) AS series
FROM raw_vault.link_eurostat_geo_series;

--GENERA CONTROLE
SELECT 'link_geography_nuts' AS table_name, COUNT(*) AS rows_count
FROM raw_vault.link_geography_nuts

UNION ALL

SELECT 'link_nuts_hierarchy', COUNT(*)
FROM raw_vault.link_nuts_hierarchy

UNION ALL

SELECT 'link_eurostat_geo_nuts', COUNT(*)
FROM raw_vault.link_eurostat_geo_nuts

UNION ALL

SELECT 'link_eurostat_geo_series', COUNT(*)
FROM raw_vault.link_eurostat_geo_series;

-- CONTROLE ANOMALIES
SELECT 'geography_nuts' AS relation, COUNT(*) AS anomalies
FROM raw_vault.link_geography_nuts l
LEFT JOIN raw_vault.hub_geography g
    ON g.geography_hk = l.geography_hk
LEFT JOIN raw_vault.hub_nuts n
    ON n.nuts_hk = l.nuts_hk
WHERE g.geography_hk IS NULL OR n.nuts_hk IS NULL

UNION ALL

SELECT 'nuts_hierarchy', COUNT(*)
FROM raw_vault.link_nuts_hierarchy l
LEFT JOIN raw_vault.hub_nuts c
    ON c.nuts_hk = l.child_nuts_hk
LEFT JOIN raw_vault.hub_nuts p
    ON p.nuts_hk = l.parent_nuts_hk
WHERE c.nuts_hk IS NULL OR p.nuts_hk IS NULL

UNION ALL

SELECT 'eurostat_geo_nuts', COUNT(*)
FROM raw_vault.link_eurostat_geo_nuts l
LEFT JOIN raw_vault.hub_eurostat_geo g
    ON g.eurostat_geo_hk = l.eurostat_geo_hk
LEFT JOIN raw_vault.hub_nuts n
    ON n.nuts_hk = l.nuts_hk
WHERE g.eurostat_geo_hk IS NULL OR n.nuts_hk IS NULL

UNION ALL

SELECT 'eurostat_geo_series', COUNT(*)
FROM raw_vault.link_eurostat_geo_series l
LEFT JOIN raw_vault.hub_eurostat_geo g
    ON g.eurostat_geo_hk = l.eurostat_geo_hk
LEFT JOIN raw_vault.hub_eurostat_series s
    ON s.eurostat_series_hk = l.eurostat_series_hk
WHERE g.eurostat_geo_hk IS NULL OR s.eurostat_series_hk IS NULL;