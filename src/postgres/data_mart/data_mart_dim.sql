CREATE SCHEMA IF NOT EXISTS data_mart;

-- =========================================================
-- 1. DIMENSION GEOGRAPHIE
-- =========================================================

CREATE TABLE IF NOT EXISTS data_mart.dim_geography (
    geography_key  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geography_code VARCHAR(20) NOT NULL,
    geography_system VARCHAR(20) NOT NULL,
    geography_name VARCHAR(255),
    geography_level VARCHAR(20),
    ags            VARCHAR(20),
    nuts1_code     VARCHAR(10),
    nuts2_code     VARCHAR(10),
    nuts3_code     VARCHAR(10),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_dim_geography
        UNIQUE (geography_system, geography_code)
);

-- =========================================================
-- 2. DIMENSION PERIODE
-- =========================================================

CREATE TABLE IF NOT EXISTS data_mart.dim_period (
    period_key       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_code      VARCHAR(20) NOT NULL UNIQUE,
    period_type      VARCHAR(10) NOT NULL,
    period_start_date DATE NOT NULL,
    period_end_date   DATE NOT NULL,
    period_year      INTEGER NOT NULL,
    period_month     SMALLINT,
    period_quarter   SMALLINT,
    period_label     VARCHAR(50) NOT NULL,

    CONSTRAINT chk_dim_period_type
        CHECK (period_type IN ('MONTH', 'YEAR')),

    CONSTRAINT chk_dim_period_dates
        CHECK (period_end_date >= period_start_date),

    CONSTRAINT chk_dim_period_month
        CHECK (
            (period_type = 'MONTH'
             AND period_month BETWEEN 1 AND 12)
            OR
            (period_type = 'YEAR'
             AND period_month IS NULL)
        )
);

-- =========================================================
-- 3. DIMENSION INDICATEUR
-- =========================================================

CREATE TABLE IF NOT EXISTS data_mart.dim_indicator (
    indicator_key  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indicator_code VARCHAR(100) NOT NULL,
    indicator_name VARCHAR(255) NOT NULL,
    source_code    VARCHAR(20) NOT NULL,
    unit            VARCHAR(30) NOT NULL,
    indicator_description TEXT,
    aggregation_rule VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_dim_indicator
        UNIQUE (source_code, indicator_code, unit)
);

-- =========================================================
-- 4. DIMENSION SOURCE
-- =========================================================

CREATE TABLE IF NOT EXISTS data_mart.dim_source (
    source_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_code  VARCHAR(20) NOT NULL UNIQUE,
    source_name  VARCHAR(100) NOT NULL,
    source_description TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);