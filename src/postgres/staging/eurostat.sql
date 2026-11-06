BEGIN;

CREATE SCHEMA IF NOT EXISTS staging;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS staging.eurostat_unemployment (
    geo             VARCHAR(10),
    region          VARCHAR(255),
    time            INTEGER,
    freq            VARCHAR(5),
    isced11         VARCHAR(20),
    sex             VARCHAR(5),
    age             VARCHAR(20),
    unit            VARCHAR(10),
    value           NUMERIC(10,2),
    status          VARCHAR(10),

    source_system   VARCHAR(50) NOT NULL DEFAULT 'EUROSTAT',
    source_file     VARCHAR(255) NOT NULL DEFAULT 'eurostat_allemagne.csv',
    load_timestamp  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_id         UUID NOT NULL DEFAULT gen_random_uuid()
);

-- Remplacer les données du précédent chargement.
TRUNCATE TABLE staging.eurostat_unemployment;

COPY staging.eurostat_unemployment (
    geo,
    region,
    time,
    freq,
    isced11,
    sex,
    age,
    unit,
    value,
    status
)
FROM '/data/processed/eurostat_allemagne.csv'
WITH (
    FORMAT CSV,
    HEADER TRUE,
    DELIMITER ';',
    ENCODING 'UTF8'
);

UPDATE staging.eurostat_unemployment
SET
    source_system = 'EUROSTAT',
    source_file = 'eurostat_allemagne.csv';

COMMIT;