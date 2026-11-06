BEGIN;

CREATE SCHEMA IF NOT EXISTS staging;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS staging.ba_arbeitslosigkeit (
    ags                     VARCHAR(20),
    ba_id                   VARCHAR(50),
    kreis                   VARCHAR(255),
    period                  DATE,
    arbeitslose             INTEGER,
    unterbeschaeftigung     INTEGER,
    source_system           VARCHAR(50) NOT NULL DEFAULT 'BA',
    source_file             VARCHAR(255) NOT NULL DEFAULT 'ba_arbeitslosigkeit.csv',
    load_timestamp          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_id                 UUID NOT NULL DEFAULT gen_random_uuid()
);

CREATE TABLE IF NOT EXISTS staging.ba_arbeitslosigkeit_raw (
    ags                     VARCHAR(20),
    ba_id                   VARCHAR(50),
    kreis                   VARCHAR(255),
    period                  VARCHAR(7),
    arbeitslose             INTEGER,
    unterbeschaeftigung     INTEGER,
    source_system           VARCHAR(50) NOT NULL DEFAULT 'BA',
    source_file             VARCHAR(255) NOT NULL DEFAULT 'ba_arbeitslosigkeit.csv',
    load_timestamp          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_id                 UUID NOT NULL DEFAULT gen_random_uuid()
);

-- Remplacer les données du précédent chargement.
TRUNCATE TABLE
    staging.ba_arbeitslosigkeit_raw,
    staging.ba_arbeitslosigkeit;

COPY staging.ba_arbeitslosigkeit_raw (
    ags,
    ba_id,
    kreis,
    period,
    arbeitslose,
    unterbeschaeftigung
)
FROM '/data/processed/ba_arbeitslosigkeit.csv'
WITH (
    FORMAT CSV,
    HEADER TRUE,
    DELIMITER ';',
    ENCODING 'UTF8'
);

INSERT INTO staging.ba_arbeitslosigkeit (
    ags,
    ba_id,
    kreis,
    period,
    arbeitslose,
    unterbeschaeftigung,
    source_system,
    source_file,
    load_timestamp,
    load_id
)
SELECT
    TRIM(ags),
    TRIM(ba_id),
    TRIM(kreis),
    TO_DATE(period || '-01', 'YYYY-MM-DD'),
    arbeitslose,
    unterbeschaeftigung,
    'BA',
    'ba_arbeitslosigkeit.csv',
    CURRENT_TIMESTAMP,
    gen_random_uuid()
FROM staging.ba_arbeitslosigkeit_raw;

COMMIT;