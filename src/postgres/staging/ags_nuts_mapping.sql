CREATE TABLE IF NOT EXISTS staging.ags_nuts_mapping (
    ags             VARCHAR(20) NOT NULL,
    ba_id           VARCHAR(50),
    kreis           VARCHAR(255) NOT NULL,
    nuts3_code      VARCHAR(10) NOT NULL,
    mapping_method  VARCHAR(50) NOT NULL,
    mapping_status  VARCHAR(30) NOT NULL,
    mapping_source  VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_ags_nuts_mapping
        PRIMARY KEY (ags)
);

-- controle
SELECT DISTINCT
    g.ags,
    g.ba_id,
    g.kreis,
    m.nuts3_code,
    CASE
        WHEN m.nuts3_code IS NOT NULL
            THEN 'CODE_MATCH'
        ELSE 'NO_MATCH'
    END AS mapping_method
FROM staging.geo_mapping g
LEFT JOIN staging.nuts3_lau m
    ON LEFT(g.ags, 5)
       =
       LEFT(LPAD(m.lau_code, 8, '0'), 5)

UNION ALL

SELECT
    '06415000' AS ags,
    '101028' AS ba_id,
    'Hanau, Brüder-Grimm-Stadt' AS kreis,
    'DE719' AS nuts3_code,
    'NAME_MATCH' AS mapping_method
ORDER BY ags;

-- alimentattion
DROP TABLE IF EXISTS staging.ags_nuts_mapping;

CREATE TABLE staging.ags_nuts_mapping AS
SELECT DISTINCT
    g.ags,
    g.ba_id,
    g.kreis,
    m.nuts3_code,
    'CODE_MATCH' AS mapping_method,
    'VALIDATED' AS mapping_status,
    'LAU_NUTS_2024' AS mapping_source
FROM staging.geo_mapping g
JOIN staging.nuts3_lau m
    ON LEFT(g.ags, 5)
       =
       LEFT(LPAD(m.lau_code, 8, '0'), 5)

UNION ALL
SELECT
    '06415000' AS ags,
    '101028' AS ba_id,
    'Hanau, Brüder-Grimm-Stadt' AS kreis,
    'DE719' AS nuts3_code,
    'NAME_MATCH' AS mapping_method,
    'VALIDATED' AS mapping_status,
    'LAU_NUTS_2024' AS mapping_source;