-- Signaturen der Satellites (fuer T2 und T10): Zeilenzahl, aktuelle Versionen
-- und MD5 ueber alle Zeilen in fester Reihenfolge. Zeilen werden als Text
-- verglichen (t::text), dadurch unabhaengig von Spaltennamen.
-- Vor und nach dem Lauf ausfuehren; die Ausgaben muessen identisch sein,
-- solange die Quelle keine neuen Monate geliefert hat.

SELECT 'sat_ba_labour_market' AS satellite,
       count(*) AS zeilen,
       count(*) FILTER (WHERE load_end_dts IS NULL) AS aktuell,
       md5(string_agg(t::text, '|' ORDER BY t::text)) AS signatur
FROM raw_vault.sat_ba_labour_market t
UNION ALL
SELECT 'sat_eurostat_unemployment', count(*),
       count(*) FILTER (WHERE load_end_dts IS NULL),
       md5(string_agg(t::text, '|' ORDER BY t::text))
FROM raw_vault.sat_eurostat_unemployment t
UNION ALL
SELECT 'sat_geography_nuts_mapping', count(*),
       count(*) FILTER (WHERE load_end_dts IS NULL),
       md5(string_agg(t::text, '|' ORDER BY t::text))
FROM raw_vault.sat_geography_nuts_mapping t
UNION ALL
SELECT 'fact_labour_market', count(*), NULL,
       md5(string_agg(
         (t.geography_key, t.period_key, t.indicator_key, t.source_key,
          t.indicator_value)::text, '|' ORDER BY
         t.geography_key, t.period_key, t.indicator_key, t.source_key))
FROM data_mart.fact_labour_market t;
