CREATE TABLE IF NOT EXISTS staging.nuts3_lau (
    nuts3_code          VARCHAR(10) NOT NULL,
    lau_code            VARCHAR(20) NOT NULL,
    lau_name_national   VARCHAR(255),
    lau_name_latin      VARCHAR(255),
    reference_year      INTEGER NOT NULL,
    source_system       VARCHAR(50) NOT NULL,
    source_file         VARCHAR(255) NOT NULL,
    load_timestamp      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_nuts3_lau
        PRIMARY KEY (nuts3_code, lau_code)
);

COPY staging.nuts3_lau (
    nuts3_code,
    lau_code,
    lau_name_national,
    lau_name_latin,
    reference_year,
    source_system,
    source_file
)
FROM '/data/processed/nuts_lau_germany.csv'
WITH (
    FORMAT CSV,
    HEADER TRUE,
    DELIMITER ';',
    ENCODING 'UTF8'
);