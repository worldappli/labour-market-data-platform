
import json
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = (
    PROJECT_ROOT
    / "data/processed/geography/germany_kreise_2026.geojson"
)

# Connexion depuis Windows vers le port publié par Docker.
# Si tu as conservé le port 5432 au lieu de 5433, adapte PORT.
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "datawarehouse",
    "user": "dataengineer",
    "password": "dataengineer_password",
}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS data_mart;

CREATE TABLE IF NOT EXISTS data_mart.geo_kreis (
    ags_kreis           VARCHAR(5) PRIMARY KEY,
    ags_ba_candidate    VARCHAR(8) NOT NULL,
    kreis_name          TEXT NOT NULL,
    kreis_type          TEXT,
    bundesland_code     VARCHAR(2),
    source              TEXT,
    reference_date      DATE,
    geojson_feature     TEXT NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

UPSERT_SQL = """
INSERT INTO data_mart.geo_kreis (
    ags_kreis,
    ags_ba_candidate,
    kreis_name,
    kreis_type,
    bundesland_code,
    source,
    reference_date,
    geojson_feature,
    loaded_at
)
VALUES %s
ON CONFLICT (ags_kreis) DO UPDATE SET
    ags_ba_candidate = EXCLUDED.ags_ba_candidate,
    kreis_name = EXCLUDED.kreis_name,
    kreis_type = EXCLUDED.kreis_type,
    bundesland_code = EXCLUDED.bundesland_code,
    source = EXCLUDED.source,
    reference_date = EXCLUDED.reference_date,
    geojson_feature = EXCLUDED.geojson_feature,
    loaded_at = CURRENT_TIMESTAMP;
"""


def main():
    if not GEOJSON_PATH.exists():
        raise FileNotFoundError(f"GeoJSON introuvable : {GEOJSON_PATH}")

    with GEOJSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError("Le fichier doit être une FeatureCollection GeoJSON.")

    rows = []
    seen = set()

    for feature in data["features"]:
        props = feature.get("properties") or {}
        ags = str(props.get("ags_kreis", "")).strip()
        candidate = str(props.get("ags_ba_candidate", "")).strip()
        name = str(props.get("kreis_name", "")).strip()

        if len(ags) != 5 or not ags.isdigit():
            raise ValueError(f"AGS invalide : {ags!r}")

        if ags in seen:
            raise ValueError(f"AGS dupliqué dans le GeoJSON : {ags}")
        seen.add(ags)

        if not candidate or not name or not feature.get("geometry"):
            raise ValueError(f"Propriétés ou géométrie manquantes pour {ags}")

        reference_date = props.get("reference_date")

        rows.append((
            ags,
            candidate,
            name,
            props.get("kreis_type"),
            props.get("bundesland_code"),
            props.get("source"),
            reference_date,
            json.dumps(feature, ensure_ascii=False, separators=(",", ":")),
        ))

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            execute_values(
                cur,
                UPSERT_SQL,
                rows,
                template=(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, "
                    "CURRENT_TIMESTAMP)"
                ),
                page_size=100,
            )

            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT ags_kreis)
                FROM data_mart.geo_kreis;
            """)
            total, unique_ags = cur.fetchone()

    print("=== CHARGEMENT GÉOGRAPHIQUE TERMINÉ ===")
    print(f"Features lues             : {len(rows)}")
    print(f"Lignes dans PostgreSQL    : {total}")
    print(f"AGS uniques en base       : {unique_ags}")
    print(f"Table                     : data_mart.geo_kreis")

    if unique_ags != total or total != 401:
        raise RuntimeError(
            "Contrôle échoué : vérifier le nombre de lignes et les AGS."
        )


if __name__ == "__main__":
    main()
