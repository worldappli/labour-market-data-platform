#!/usr/bin/env python3
"""Transform BKG VG250 GeoPackage to a Kreis-level GeoJSON for mapping.

Usage:
  python geography_transform.py --input data/raw/geography/DE_VG250.gpkg \
      --output data/processed/geography/germany_kreise.geojson \
      --simplify-meters 100

The source layer is kept unchanged. Features are dissolved by the BKG 5-digit
Kreis AGS, simplified in the source projected CRS, then reprojected to WGS84.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to source BKG GeoPackage")
    parser.add_argument("--output", required=True, help="Output GeoJSON path")
    parser.add_argument("--layer", default="vg250_krs", help="Source layer (default: vg250_krs)")
    parser.add_argument("--simplify-meters", type=float, default=100.0,
                        help="Geometry simplification tolerance in source CRS units (default: 100 m)")
    parser.add_argument("--qc-report", default=None, help="Optional JSON QC report path")
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    if not source.is_file():
        raise FileNotFoundError(f"Fichier source introuvable : {source}")
    if args.simplify_meters < 0:
        raise ValueError("--simplify-meters doit être positif ou nul")

    output.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.read_file(source, layer=args.layer)
    required = {"AGS", "GEN", "BEZ", "LKZ", "geom"}
    # GeoPandas exposes the geometry column as 'geometry', not 'geom'.
    missing = required - (set(gdf.columns) | {"geom"})
    if missing:
        raise ValueError(f"Colonnes absentes dans {args.layer}: {sorted(missing)}")
    if gdf.crs is None:
        raise ValueError("Le GeoPackage ne déclare pas de système de coordonnées")

    input_rows = len(gdf)
    input_unique_ags = int(gdf["AGS"].nunique(dropna=True))
    if gdf["AGS"].isna().any():
        gdf = gdf.loc[gdf["AGS"].notna()].copy()
    gdf["AGS"] = gdf["AGS"].astype(str).str.strip()
    gdf = gdf.loc[gdf["AGS"].str.fullmatch(r"\d{5}")].copy()
    if gdf.empty:
        raise ValueError("Aucune valeur AGS à 5 chiffres après validation")

    # 433 features in this source layer include multiple components for some AGS.
    # Dissolve all components for each 5-digit Kreis code into one geometry.
    kreise = gdf[["AGS", "GEN", "BEZ", "LKZ", "geometry"]].dissolve(
        by="AGS", as_index=False, aggfunc={"GEN": "first", "BEZ": "first", "LKZ": "first"}
    )
    kreise = kreise.rename(columns={
        "AGS": "ags_kreis",
        "GEN": "kreis_name",
        "BEZ": "kreis_type",
        "LKZ": "bundesland_code",
    })
    # Candidate key used by this project: 5-digit Kreis code + '000' => 8-digit AGS.
    # It is a candidate join key, not proof that every historical BA territory matches.
    kreise["ags_ba_candidate"] = kreise["ags_kreis"] + "000"
    kreise["source"] = "BKG VG250"
    kreise["source_layer"] = args.layer
    kreise["reference_date"] = "2025-12-31"  # gpkg_contents description in uploaded file

    invalid_before = int((~kreise.geometry.is_valid).sum())
    empty_before = int(kreise.geometry.is_empty.sum())
    if invalid_before or empty_before:
        raise ValueError(f"Géométries invalides/vides après dissolve: invalides={invalid_before}, vides={empty_before}")

    # Simplify in projected CRS (the uploaded source is EPSG:25832), not in degrees.
    if args.simplify_meters > 0:
        kreise["geometry"] = kreise.geometry.simplify(
            tolerance=args.simplify_meters, preserve_topology=True
        )
    simplified_invalid = int((~kreise.geometry.is_valid).sum())
    if simplified_invalid:
        raise ValueError(f"Géométries invalides après simplification: {simplified_invalid}")

    source_crs = str(kreise.crs)
    kreise = kreise.to_crs("EPSG:4326")
    # Stable, useful properties only; do not export the source's unused attributes.
    keep = ["ags_kreis", "ags_ba_candidate", "kreis_name", "kreis_type",
            "bundesland_code", "source", "source_layer", "reference_date", "geometry"]
    kreise = kreise[keep].sort_values("ags_kreis").reset_index(drop=True)
    kreise.to_file(output, driver="GeoJSON", index=False, RFC7946=True)

    report = {
        "source_file": source.name,
        "source_layer": args.layer,
        "source_reference_date": "2025-12-31",
        "source_crs": source_crs,
        "output_crs": "EPSG:4326",
        "input_feature_count": input_rows,
        "input_unique_ags_count": input_unique_ags,
        "output_feature_count": len(kreise),
        "output_unique_ags_count": int(kreise["ags_kreis"].nunique()),
        "invalid_geometries_before_simplification": invalid_before,
        "empty_geometries_before_simplification": empty_before,
        "invalid_geometries_after_simplification": simplified_invalid,
        "simplify_tolerance_meters": args.simplify_meters,
        "output_file": str(output),
        "output_size_bytes": output.stat().st_size,
        "notes": [
            "Les géométries sont dissoutes par AGS BKG à 5 chiffres.",
            "ags_ba_candidate est une clé candidate de jointure (AGS à 5 chiffres + 000), à valider avec la source BA.",
            "La référence géographique est au 2025-12-31; vérifier les changements territoriaux postérieurs, notamment Hanau."
        ],
    }
    report_text = json.dumps(report, ensure_ascii=False, indent=2)
    print(report_text)
    if args.qc_report:
        report_path = Path(args.qc_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()