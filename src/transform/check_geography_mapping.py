
import json
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "data" / "processed" / "geography" / "germany_kreise_2026.geojson"

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "datawarehouse",
    "user": "dataengineer",
    "password": "dataengineer_password",
}


def main():
    with GEOJSON.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    geo_codes = {
        feature["properties"]["ags_ba_candidate"]
        for feature in geojson["features"]
        if feature.get("properties", {}).get("ags_ba_candidate")
    }

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ags
                FROM staging.ags_nuts_mapping
                WHERE mapping_status = 'VALIDATED'
            """)
            ba_codes = {row[0].strip() for row in cur.fetchall()}

    matched = ba_codes & geo_codes
    ba_without_geometry = ba_codes - geo_codes
    geometry_without_ba = geo_codes - ba_codes

    print("=== CONTROLE GEOGRAPHIQUE ===")
    print(f"Territoires BA validés : {len(ba_codes)}")
    print(f"Géométries GeoJSON : {len(geo_codes)}")
    print(f"Correspondances exactes : {len(matched)}")
    print(f"Territoires BA sans géométrie : {len(ba_without_geometry)}")
    print(f"Géométries sans BA : {len(geometry_without_ba)}")

    if ba_without_geometry:
        print("\nAGS BA sans géométrie :")
        for code in sorted(ba_without_geometry):
            print(" -", code)

    if geometry_without_ba:
        print("\nCodes géographiques sans BA :")
        for code in sorted(geometry_without_ba):
            print(" -", code)


if __name__ == "__main__":
    main()
