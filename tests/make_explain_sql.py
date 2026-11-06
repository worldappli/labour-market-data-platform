#!/usr/bin/env python3
"""
Erzeugt die SQL-Dateien fuer die Laufzeitanalyse des Faktenladens
(aus src/postgres/data_mart/data_mart_fact.sql).

Aufruf im Projektstamm:   python tests/make_explain_sql.py
Ausgabe in tests/explain/:
  1_plan.sql          nur Plan (EXPLAIN ohne ANALYZE), Sekunden
  2_views.sql         Laufzeit der beiden Views allein
  3_vorher.sql        EXPLAIN ANALYZE beider INSERTs (Ist-Zustand)
  4_nachher.sql       EXPLAIN ANALYZE mit materialisierter Jahres-Aggregation
  5_aequivalenz.sql   Beweis, dass die optimierte Abfrage dieselben Zeilen liefert
                      wie der aktuelle Datenbestand (EXCEPT ALL in beide Richtungen)

Alle Dateien enden mit ROLLBACK und aendern keine Daten. Trotzdem nur auf
der Kopie dw_test ausfuehren (siehe Anleitung).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "postgres" / "data_mart" / "data_mart_fact.sql"
OUT = ROOT / "tests" / "explain"

text = SRC.read_text(encoding="utf-8")
stmts = []
for m in re.finditer(r"INSERT INTO data_mart\.fact_labour_market", text):
    end = text.index(";", m.start())
    stmts.append(text[m.start():end].strip())
if len(stmts) != 2:
    raise SystemExit(f"Erwartet 2 INSERT-Anweisungen, gefunden: {len(stmts)}")
s1, s2 = stmts

OUT.mkdir(parents=True, exist_ok=True)

(OUT / "1_plan.sql").write_text(
    "\\timing on\nBEGIN;\nEXPLAIN\n" + s1 + ";\nROLLBACK;\n", encoding="utf-8")

(OUT / "2_views.sql").write_text(
    "\\timing on\n"
    "EXPLAIN (ANALYZE, BUFFERS)\n"
    "SELECT count(*) FROM business_vault.vw_ba_annual_indicators;\n"
    "EXPLAIN (ANALYZE, BUFFERS)\n"
    "SELECT count(*) FROM business_vault.vw_labour_market_indicators;\n",
    encoding="utf-8")

(OUT / "3_vorher.sql").write_text(
    "\\timing on\nSET statement_timeout = 0;\n"
    "BEGIN;\nEXPLAIN (ANALYZE, BUFFERS)\n" + s1 + ";\nROLLBACK;\n"
    "BEGIN;\nEXPLAIN (ANALYZE, BUFFERS)\n" + s2 + ";\nROLLBACK;\n",
    encoding="utf-8")

s1_opt = s1.replace("business_vault.vw_ba_annual_indicators AS ba",
                    "tmp_ba_annual AS ba")
if s1_opt == s1:
    raise SystemExit("Join auf vw_ba_annual_indicators nicht gefunden")

(OUT / "4_nachher.sql").write_text(
    "\\timing on\nSET statement_timeout = 0;\nBEGIN;\n"
    "CREATE TEMP TABLE tmp_ba_annual AS\n"
    "  SELECT * FROM business_vault.vw_ba_annual_indicators;\n"
    "CREATE INDEX ON tmp_ba_annual (ags, year);\n"
    "ANALYZE tmp_ba_annual;\n"
    "EXPLAIN (ANALYZE, BUFFERS)\n" + s1_opt + ";\nROLLBACK;\n",
    encoding="utf-8")

print("Erzeugt in", OUT)
for f in sorted(OUT.glob("*.sql")):
    print(" -", f.name)


# --- 5: Aequivalenz der optimierten Abfrage ---------------------------------
cols_start = s1_opt.index("(") + 1
cols_end = s1_opt.index(")", cols_start)
cols = [c.strip() for c in s1_opt[cols_start:cols_end].split(",") if c.strip()]
sel_start = s1_opt.index("SELECT", cols_end)
sel_end = s1_opt.index("ON CONFLICT")
select_part = s1_opt[sel_start:sel_end].strip()
col_list = ", ".join(cols)

(OUT / "5_aequivalenz.sql").write_text(
    "\\timing on\nBEGIN;\n"
    "CREATE TEMP TABLE tmp_ba_annual AS\n"
    "  SELECT * FROM business_vault.vw_ba_annual_indicators;\n"
    "CREATE INDEX ON tmp_ba_annual (ags, year);\n"
    "ANALYZE tmp_ba_annual;\n\n"
    "-- Ergebnis der OPTIMIERTEN Abfrage (ohne Schreiben in die Faktentabelle)\n"
    "CREATE TEMP TABLE neu (" + col_list + ") AS\n" + select_part + ";\n\n"
    "-- Aktueller Bestand im Geltungsbereich dieser Abfrage\n"
    "CREATE TEMP TABLE bestand AS\n"
    "  SELECT " + col_list + "\n"
    "  FROM data_mart.fact_labour_market\n"
    "  WHERE indicator_key IN (SELECT DISTINCT indicator_key FROM neu);\n\n"
    "SELECT (SELECT count(*) FROM neu)     AS zeilen_neu,\n"
    "       (SELECT count(*) FROM bestand) AS zeilen_bestand;\n\n"
    "-- Beide Differenzen muessen 0 Zeilen liefern:\n"
    "SELECT 'neu minus bestand' AS richtung, count(*) AS abweichungen FROM (\n"
    "  SELECT " + col_list + " FROM neu\n"
    "  EXCEPT ALL\n"
    "  SELECT " + col_list + " FROM bestand) a\n"
    "UNION ALL\n"
    "SELECT 'bestand minus neu', count(*) FROM (\n"
    "  SELECT " + col_list + " FROM bestand\n"
    "  EXCEPT ALL\n"
    "  SELECT " + col_list + " FROM neu) b;\n"
    "ROLLBACK;\n",
    encoding="utf-8")
print(" - 5_aequivalenz.sql")
