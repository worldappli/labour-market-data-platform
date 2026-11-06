CREATE TABLE staging.geo_mapping (
    ags             VARCHAR(20) NOT NULL,
    ba_id           VARCHAR(50),
    kreis           VARCHAR(255) NOT NULL,

    nuts2_code      VARCHAR(10),
    nuts2_region    VARCHAR(255),

    mapping_status  VARCHAR(30) NOT NULL DEFAULT 'TO_VALIDATE',
    mapping_source  VARCHAR(100),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ags)
);

ALTER TABLE staging.geo_mapping
ADD COLUMN IF NOT EXISTS nuts3_code VARCHAR(10);

INSERT INTO staging.geo_mapping (
    ags,
    ba_id,
    kreis
)
SELECT
    ags,
    ba_id,
    kreis
FROM staging.ba_arbeitslosigkeit
GROUP BY
    ags,
    ba_id,
    kreis;

 SELECT
    g.ags,
    g.ba_id,
    g.kreis,
    m.nuts3_code,
    m.lau_code,
    m.lau_name_national
FROM staging.geo_mapping g
LEFT JOIN staging.nuts3_lau m
    ON LEFT(g.ags, 5)
       =
       LEFT(LPAD(m.lau_code, 8, '0'), 5)
ORDER BY g.ags
LIMIT 30;

UPDATE staging.geo_mapping g
SET
    nuts3_code = m.nuts3_code,
    mapping_status = m.mapping_status,
    mapping_source = m.mapping_source
FROM staging.ags_nuts_mapping m
WHERE g.ags = m.ags;

UPDATE staging.geo_mapping g
SET
    nuts2_code = n.parent_code
FROM staging.nuts_reference n
WHERE g.nuts3_code = n.nuts_code
  AND n.nuts_level = 3;

  UPDATE staging.geo_mapping
SET mapping_status = 'VALIDATED'
WHERE nuts3_code IS NOT NULL
  AND nuts2_code IS NOT NULL;

  -- control

 SELECT
    COUNT(*) AS total_ags,
    COUNT(nuts3_code) AS avec_nuts3,
    COUNT(nuts2_code) AS avec_nuts2,
    COUNT(*) FILTER (
        WHERE nuts3_code IS NULL
    ) AS sans_nuts3,
    COUNT(*) FILTER (
        WHERE nuts2_code IS NULL
    ) AS sans_nuts2
FROM staging.geo_mapping;

-- control general
SELECT
    g.ags,
    g.kreis,
    g.nuts3_code,
    n3.parent_code AS nuts2_code,
    n2.parent_code AS nuts1_code
FROM staging.geo_mapping g
JOIN staging.nuts_reference n3
    ON g.nuts3_code = n3.nuts_code
   AND n3.nuts_level = 3
JOIN staging.nuts_reference n2
    ON n3.parent_code = n2.nuts_code
   AND n2.nuts_level = 2
ORDER BY g.ags
LIMIT 20;