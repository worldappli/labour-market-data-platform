BEGIN;

-- =========================================================
-- 0. SCHEMA ET EXTENSION
-- =========================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS raw_vault;

COMMENT ON SCHEMA raw_vault IS
'Data Vault 2.0 : Hubs, Links et Satellites';

-- Schémas réservés aux étapes ultérieures
CREATE SCHEMA IF NOT EXISTS business_vault;
CREATE SCHEMA IF NOT EXISTS data_mart;


-- =========================================================
-- 1. HUBS
-- =========================================================

-- 1.1. Territoires BA : clé métier AGS
CREATE TABLE IF NOT EXISTS raw_vault.hub_geography (
    geography_hk  CHAR(64) PRIMARY KEY,
    ags           VARCHAR(20) NOT NULL UNIQUE,
    load_dts      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL
);

COMMENT ON TABLE raw_vault.hub_geography IS
'Hub des territoires BA, identifiés par leur AGS';


-- 1.2. Référentiel NUTS : clé métier nuts_code
CREATE TABLE IF NOT EXISTS raw_vault.hub_nuts (
    nuts_hk       CHAR(64) PRIMARY KEY,
    nuts_code     VARCHAR(10) NOT NULL UNIQUE,
    load_dts      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL
);

COMMENT ON TABLE raw_vault.hub_nuts IS
'Hub des codes NUTS de niveau 1, 2 et 3';


-- 1.3. Géographies natives Eurostat
-- Exemple : DE, DE1, DE11, DE111 selon le jeu de données
CREATE TABLE IF NOT EXISTS raw_vault.hub_eurostat_geo (
    eurostat_geo_hk CHAR(64) PRIMARY KEY,
    geo_code        VARCHAR(10) NOT NULL UNIQUE,
    load_dts        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source   VARCHAR(100) NOT NULL
);

COMMENT ON TABLE raw_vault.hub_eurostat_geo IS
'Hub des codes géographiques natifs de la source Eurostat';


-- 1.4. Séries statistiques Eurostat
-- Clé métier composée des dimensions :
-- freq + isced11 + sex + age + unit
CREATE TABLE IF NOT EXISTS raw_vault.hub_eurostat_series (
    eurostat_series_hk CHAR(64) PRIMARY KEY,
    series_bk          VARCHAR(500) NOT NULL UNIQUE,
    load_dts           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source      VARCHAR(100) NOT NULL
);

COMMENT ON TABLE raw_vault.hub_eurostat_series IS
'Hub des combinaisons de dimensions statistiques Eurostat';


-- =========================================================
-- 2. LINKS
-- =========================================================

-- 2.1. Association entre territoire BA et NUTS
CREATE TABLE IF NOT EXISTS raw_vault.link_geography_nuts (
    geography_nuts_hk CHAR(64) PRIMARY KEY,
    geography_hk      CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_geography (geography_hk),
    nuts_hk           CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_nuts (nuts_hk),
    load_dts          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source     VARCHAR(100) NOT NULL,

    CONSTRAINT uq_link_geography_nuts
        UNIQUE (geography_hk, nuts_hk)
);

COMMENT ON TABLE raw_vault.link_geography_nuts IS
'Association entre un AGS BA et un code NUTS';


-- 2.2. Hiérarchie NUTS : enfant vers parent
CREATE TABLE IF NOT EXISTS raw_vault.link_nuts_hierarchy (
    nuts_hierarchy_hk CHAR(64) PRIMARY KEY,
    child_nuts_hk     CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_nuts (nuts_hk),
    parent_nuts_hk    CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_nuts (nuts_hk),
    load_dts          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source     VARCHAR(100) NOT NULL,

    CONSTRAINT uq_link_nuts_hierarchy
        UNIQUE (child_nuts_hk, parent_nuts_hk),

    CONSTRAINT chk_nuts_not_own_parent
        CHECK (child_nuts_hk <> parent_nuts_hk)
);

COMMENT ON TABLE raw_vault.link_nuts_hierarchy IS
'Hiérarchie géographique NUTS : NUTS3 vers NUTS2, NUTS2 vers NUTS1';


-- 2.3. Géographie Eurostat vers code NUTS canonique
-- Le code DE, par exemple, n'a pas de correspondance NUTS1/2/3.
CREATE TABLE IF NOT EXISTS raw_vault.link_eurostat_geo_nuts (
    eurostat_geo_nuts_hk CHAR(64) PRIMARY KEY,
    eurostat_geo_hk      CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_eurostat_geo (eurostat_geo_hk),
    nuts_hk              CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_nuts (nuts_hk),
    load_dts             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source        VARCHAR(100) NOT NULL,

    CONSTRAINT uq_link_eurostat_geo_nuts
        UNIQUE (eurostat_geo_hk, nuts_hk)
);

COMMENT ON TABLE raw_vault.link_eurostat_geo_nuts IS
'Correspondance entre un code géographique Eurostat et un code NUTS';


-- 2.4. Association géographie et série statistique Eurostat
-- La période sera conservée dans le Satellite de mesures.
CREATE TABLE IF NOT EXISTS raw_vault.link_eurostat_geo_series (
    eurostat_geo_series_hk CHAR(64) PRIMARY KEY,
    eurostat_geo_hk        CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_eurostat_geo (eurostat_geo_hk),
    eurostat_series_hk     CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_eurostat_series
            (eurostat_series_hk),
    load_dts               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source          VARCHAR(100) NOT NULL,

    CONSTRAINT uq_link_eurostat_geo_series
        UNIQUE (eurostat_geo_hk, eurostat_series_hk)
);

COMMENT ON TABLE raw_vault.link_eurostat_geo_series IS
'Association entre géographie et série statistique Eurostat';


-- =========================================================
-- 3. SATELLITES
-- =========================================================

-- 3.1. Attributs descriptifs des territoires BA
CREATE TABLE IF NOT EXISTS raw_vault.sat_geography_ba (
    geography_hk  CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_geography (geography_hk),
    load_dts      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts  TIMESTAMPTZ,
    hashdiff      CHAR(64) NOT NULL,
    ba_id         VARCHAR(50),
    kreis         VARCHAR(255) NOT NULL,
    record_source VARCHAR(100) NOT NULL,

    PRIMARY KEY (geography_hk, load_dts),

    CONSTRAINT chk_sat_geography_ba_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_geography_ba IS
'Historique des attributs descriptifs des territoires BA';


-- 3.2. Attributs du référentiel NUTS
CREATE TABLE IF NOT EXISTS raw_vault.sat_nuts (
    nuts_hk        CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_nuts (nuts_hk),
    load_dts       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts   TIMESTAMPTZ,
    hashdiff       CHAR(64) NOT NULL,
    nuts_level     SMALLINT NOT NULL,
    country_code   VARCHAR(5) NOT NULL,
    reference_year INTEGER NOT NULL,
    record_source  VARCHAR(100) NOT NULL,

    PRIMARY KEY (nuts_hk, load_dts),

    CONSTRAINT chk_sat_nuts_level
        CHECK (nuts_level IN (1, 2, 3)),

    CONSTRAINT chk_sat_nuts_country
        CHECK (country_code = 'DE'),

    CONSTRAINT chk_sat_nuts_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_nuts IS
'Attributs et année de référence des codes NUTS';


-- 3.3. Historique de la méthode et du statut du mapping AGS-NUTS
CREATE TABLE IF NOT EXISTS raw_vault.sat_geography_nuts_mapping (
    geography_nuts_hk CHAR(64) NOT NULL
        REFERENCES raw_vault.link_geography_nuts
            (geography_nuts_hk),
    load_dts          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts      TIMESTAMPTZ,
    hashdiff          CHAR(64) NOT NULL,
    mapping_method    VARCHAR(50) NOT NULL,
    mapping_status    VARCHAR(30) NOT NULL,
    mapping_source    VARCHAR(100) NOT NULL,
    record_source     VARCHAR(100) NOT NULL,

    PRIMARY KEY (geography_nuts_hk, load_dts),

    CONSTRAINT chk_sat_geo_nuts_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_geography_nuts_mapping IS
'Historique de validation et de provenance du mapping AGS-NUTS';


-- 3.4. Mesures mensuelles BA
-- Satellite multi-actif :
-- plusieurs périodes par geography_hk sont autorisées.
CREATE TABLE IF NOT EXISTS raw_vault.sat_ba_labour_market (
    geography_hk        CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_geography (geography_hk),
    period              DATE NOT NULL,
    load_dts             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts         TIMESTAMPTZ,
    hashdiff             CHAR(64) NOT NULL,
    arbeitslose          BIGINT NOT NULL,
    unterbeschaeftigung  BIGINT,
    record_source        VARCHAR(100) NOT NULL,

    PRIMARY KEY (geography_hk, period, load_dts),

    CONSTRAINT chk_sat_ba_arbeitslose
        CHECK (arbeitslose >= 0),

    CONSTRAINT chk_sat_ba_unterbeschaeftigung
        CHECK (
            unterbeschaeftigung IS NULL
            OR unterbeschaeftigung >= 0
        ),

    CONSTRAINT chk_sat_ba_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_ba_labour_market IS
'Mesures mensuelles BA au grain AGS + période, avec historisation';


-- 3.5. Libellés géographiques Eurostat
CREATE TABLE IF NOT EXISTS raw_vault.sat_eurostat_geo (
    eurostat_geo_hk CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_eurostat_geo (eurostat_geo_hk),
    load_dts        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts    TIMESTAMPTZ,
    hashdiff        CHAR(64) NOT NULL,
    region          VARCHAR(255),
    record_source   VARCHAR(100) NOT NULL,

    PRIMARY KEY (eurostat_geo_hk, load_dts),

    CONSTRAINT chk_sat_eurostat_geo_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_eurostat_geo IS
'Libellés descriptifs des codes géographiques Eurostat';


-- 3.6. Dimensions des séries Eurostat
CREATE TABLE IF NOT EXISTS raw_vault.sat_eurostat_series (
    eurostat_series_hk CHAR(64) NOT NULL
        REFERENCES raw_vault.hub_eurostat_series
            (eurostat_series_hk),
    load_dts           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts       TIMESTAMPTZ,
    hashdiff           CHAR(64) NOT NULL,
    freq               VARCHAR(5) NOT NULL,
    isced11            VARCHAR(20) NOT NULL,
    sex                VARCHAR(5) NOT NULL,
    age                VARCHAR(20) NOT NULL,
    unit               VARCHAR(10) NOT NULL,
    record_source      VARCHAR(100) NOT NULL,

    PRIMARY KEY (eurostat_series_hk, load_dts),

    CONSTRAINT chk_sat_eurostat_series_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_eurostat_series IS
'Dimensions freq, isced11, sex, age et unit des séries Eurostat';


-- 3.7. Mesures Eurostat
-- Satellite multi-actif :
-- plusieurs périodes pour un même couple géographie-série.
CREATE TABLE IF NOT EXISTS raw_vault.sat_eurostat_unemployment (
    eurostat_geo_series_hk CHAR(64) NOT NULL
        REFERENCES raw_vault.link_eurostat_geo_series
            (eurostat_geo_series_hk),
    period_bk              VARCHAR(20) NOT NULL,
    load_dts               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_dts           TIMESTAMPTZ,
    hashdiff               CHAR(64) NOT NULL,
    value                  NUMERIC(10, 2) NOT NULL,
    status                 VARCHAR(10),
    record_source          VARCHAR(100) NOT NULL,

    PRIMARY KEY (eurostat_geo_series_hk, period_bk, load_dts),

    CONSTRAINT chk_sat_eurostat_value
        CHECK (value >= 0 AND value <= 100),

    CONSTRAINT chk_sat_eurostat_dates
        CHECK (load_end_dts IS NULL OR load_end_dts > load_dts)
);

COMMENT ON TABLE raw_vault.sat_eurostat_unemployment IS
'Valeurs Eurostat au grain géographie + série + période, avec historisation';


-- =========================================================
-- 4. INDEX DE SUPPORT
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_link_geo_nuts_nuts
    ON raw_vault.link_geography_nuts (nuts_hk);

CREATE INDEX IF NOT EXISTS idx_link_nuts_hierarchy_parent
    ON raw_vault.link_nuts_hierarchy (parent_nuts_hk);

CREATE INDEX IF NOT EXISTS idx_link_eurostat_geo_nuts_nuts
    ON raw_vault.link_eurostat_geo_nuts (nuts_hk);

CREATE INDEX IF NOT EXISTS idx_sat_ba_period
    ON raw_vault.sat_ba_labour_market (period);

CREATE INDEX IF NOT EXISTS idx_sat_eurostat_period
    ON raw_vault.sat_eurostat_unemployment (period_bk);


COMMIT;