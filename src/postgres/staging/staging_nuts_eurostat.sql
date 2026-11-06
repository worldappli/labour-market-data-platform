CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.nuts_reference (
    nuts_code       VARCHAR(10) NOT NULL,
    nuts_level      SMALLINT NOT NULL,
    country_code    VARCHAR(5) NOT NULL,
    parent_code     VARCHAR(10),
    reference_year  INTEGER NOT NULL,
    source_system   VARCHAR(50) NOT NULL,
    source_file     VARCHAR(255) NOT NULL,
    load_timestamp  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_nuts_reference
        PRIMARY KEY (nuts_code),

    CONSTRAINT chk_nuts_level
        CHECK (nuts_level IN (1, 2, 3)),

    CONSTRAINT chk_country_code
        CHECK (country_code = 'DE')
);

COPY staging.nuts_reference (
    nuts_code,
    nuts_level,
    country_code,
    parent_code,
    reference_year,
    source_system,
    source_file
)
FROM '/data/processed/nuts_germany.csv'
WITH (
    FORMAT CSV,
    HEADER TRUE,
    DELIMITER ';',
    ENCODING 'UTF8'
);

SELECT
    nuts_level,
    COUNT(*) AS nombre
FROM staging.nuts_reference
GROUP BY nuts_level
ORDER BY nuts_level;

SELECT *
FROM staging.nuts_reference
ORDER BY nuts_level, nuts_code;