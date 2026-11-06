CREATE SCHEMA IF NOT EXISTS business_vault;

CREATE TABLE IF NOT EXISTS business_vault.business_rules (
    rule_code       VARCHAR(20) PRIMARY KEY,
    rule_name       VARCHAR(150) NOT NULL,
    rule_description TEXT NOT NULL,
    source_objects  TEXT NOT NULL,
    target_object   VARCHAR(150),
    validation_rule TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- LES REGLES INITIAL
INSERT INTO business_vault.business_rules (
    rule_code,
    rule_name,
    rule_description,
    source_objects,
    target_object,
    validation_rule
)
VALUES
(
    'BV-GEO-001',
    'Mapping géographique BA vers NUTS',
    'Rapprocher les territoires BA identifiés par AGS des niveaux NUTS3, NUTS2 et NUTS1 à partir du mapping validé et de la hiérarchie géographique.',
    'raw_vault.hub_geography; raw_vault.hub_nuts; raw_vault.link_geography_nuts; raw_vault.link_nuts_hierarchy',
    'business_vault.vw_ba_geography_hierarchy',
    'Tous les AGS attendus doivent être traçables. Les correspondances ambiguës ou absentes doivent être signalées.'
),
(
    'BV-TIME-001',
    'Comparabilité temporelle',
    'Conserver la granularité mensuelle BA et annuelle Eurostat. Calculer les agrégats annuels BA selon une méthode explicitement documentée.',
    'raw_vault.sat_ba_labour_market; raw_vault.sat_eurostat_unemployment',
    'business_vault.vw_ba_annual_indicators',
    'Documenter les mois disponibles et ne pas présenter une année incomplète comme une moyenne annuelle complète.'
),
(
    'BV-MET-001',
    'Distinction des indicateurs de chômage',
    'Séparer les effectifs administratifs BA des taux de chômage harmonisés Eurostat et conserver les dimensions statistiques Eurostat.',
    'raw_vault.sat_ba_labour_market; raw_vault.sat_eurostat_unemployment; raw_vault.sat_eurostat_series',
    'business_vault.vw_labour_market_indicators',
    'Ne jamais additionner des taux régionaux ni assimiler un effectif BA à un taux Eurostat.'
),
(
    'BV-DQ-001',
    'Traçabilité et qualité métier',
    'Conserver la provenance des données, les méthodes d''agrégation et les anomalies détectées.',
    'raw_vault; staging',
    'business_vault.quality_results',
    'Toute transformation doit être reproductible et les anomalies doivent être visibles.'
)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    rule_description = EXCLUDED.rule_description,
    source_objects = EXCLUDED.source_objects,
    target_object = EXCLUDED.target_object,
    validation_rule = EXCLUDED.validation_rule;

 -- controle
 SELECT
    rule_code,
    rule_name,
    target_object,
    is_active
FROM business_vault.business_rules
ORDER BY rule_code;

-- view
CREATE SCHEMA IF NOT EXISTS business_vault;

CREATE OR REPLACE VIEW business_vault.vw_ba_geography_hierarchy AS
SELECT
    -- Identité du territoire BA
    g.ags,
    sba.ba_id,
    sba.kreis,

    -- Niveau NUTS 3
    n3.nuts_code AS nuts3_code,
    sn3.nuts_level AS nuts3_level,

    -- Niveau NUTS 2
    n2.nuts_code AS nuts2_code,
    sn2.nuts_level AS nuts2_level,

    -- Niveau NUTS 1
    n1.nuts_code AS nuts1_code,
    sn1.nuts_level AS nuts1_level,

    -- Informations sur le mapping
    sm.mapping_method,
    sm.mapping_status,
    sm.mapping_source,

    -- Métadonnées
    g.record_source AS ba_record_source,
    lgn.record_source AS geography_mapping_source

FROM raw_vault.hub_geography AS g

-- Attributs descriptifs BA
LEFT JOIN raw_vault.sat_geography_ba AS sba
    ON sba.geography_hk = g.geography_hk
   AND sba.load_end_dts IS NULL

-- Association AGS -> NUTS3
LEFT JOIN raw_vault.link_geography_nuts AS lgn
    ON lgn.geography_hk = g.geography_hk

LEFT JOIN raw_vault.hub_nuts AS n3
    ON n3.nuts_hk = lgn.nuts_hk

LEFT JOIN raw_vault.sat_nuts AS sn3
    ON sn3.nuts_hk = n3.nuts_hk
   AND sn3.load_end_dts IS NULL

-- Métadonnées du mapping AGS -> NUTS3
LEFT JOIN raw_vault.sat_geography_nuts_mapping AS sm
    ON sm.geography_nuts_hk = lgn.geography_nuts_hk
   AND sm.load_end_dts IS NULL

-- Hiérarchie NUTS3 -> NUTS2
LEFT JOIN raw_vault.link_nuts_hierarchy AS l23
    ON l23.child_nuts_hk = n3.nuts_hk

LEFT JOIN raw_vault.hub_nuts AS n2
    ON n2.nuts_hk = l23.parent_nuts_hk

LEFT JOIN raw_vault.sat_nuts AS sn2
    ON sn2.nuts_hk = n2.nuts_hk
   AND sn2.load_end_dts IS NULL

-- Hiérarchie NUTS2 -> NUTS1
LEFT JOIN raw_vault.link_nuts_hierarchy AS l12
    ON l12.child_nuts_hk = n2.nuts_hk

LEFT JOIN raw_vault.hub_nuts AS n1
    ON n1.nuts_hk = l12.parent_nuts_hk

LEFT JOIN raw_vault.sat_nuts AS sn1
    ON sn1.nuts_hk = n1.nuts_hk
   AND sn1.load_end_dts IS NULL;

-- schow view
SELECT *
FROM business_vault.vw_ba_geography_hierarchy
ORDER BY ags
LIMIT 20;