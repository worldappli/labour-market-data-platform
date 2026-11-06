
#!/usr/bin/env python3
"""
Met à jour les géométries des districts de Hesse dans le GeoJSON national.

Entrées :
  data/processed/geography/germany_kreise.geojson
  data/raw/geography/hessen/landkreise_hessen.geojson

Sorties :
  data/processed/geography/germany_kreise_2026.geojson
  data/processed/geography/hessen_geography_qc_report.json

La source nationale originale n'est jamais modifiée.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_NATIONAL_INPUT = (
    PROJECT_ROOT / "data/processed/geography/germany_kreise.geojson"
)
DEFAULT_HESSEN_INPUT = (
    PROJECT_ROOT / "data/raw/geography/hessen/landkreise_hessen.geojson"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/processed/geography/germany_kreise_2026.geojson"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "data/processed/geography/hessen_geography_qc_report.json"
)

HESSEN_CODE = "HE"
HESSEN_AGS_PREFIX = "06"
SOURCE_NAME = "Geoportal Hessen – Verwaltungsgrenzen"
SOURCE_LAYER = "borders:landkreiseHE_wfs"
REFERENCE_DATE = "2026-06-17"


def load_geojson(path: Path) -> dict[str, Any]:
    """Charge et valide la structure générale d'un GeoJSON."""
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} n'est pas une FeatureCollection GeoJSON.")

    if not isinstance(data.get("features"), list):
        raise ValueError(f"Le champ 'features' est absent ou invalide : {path}")

    return data


def normalize_kreis_number(value: Any) -> str:
    """Normalise le numéro de district sur trois chiffres."""
    if value is None:
        raise ValueError("KREIS_NR est absent.")

    number = str(value).strip()

    if not number.isdigit() or len(number) > 3:
        raise ValueError(f"KREIS_NR invalide : {value!r}")

    return number.zfill(3)


def transform_hessen_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """Convertit une feature de Hesse vers le format national du projet."""
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")

    if not geometry or not geometry.get("type") or not geometry.get("coordinates"):
        raise ValueError(
            f"Géométrie absente pour {properties.get('KREIS_BZ', 'district inconnu')}"
        )

    kreis_nr = normalize_kreis_number(properties.get("KREIS_NR"))
    ags_kreis = HESSEN_AGS_PREFIX + kreis_nr
    ags_ba_candidate = ags_kreis + "000"

    kreis_name = str(properties.get("KREIS_BZ") or "").strip()

    if not kreis_name:
        raise ValueError(f"KREIS_BZ absent pour le district {ags_kreis}")

    is_independent_city = "kreisfreie stadt" in kreis_name.casefold()

    if is_independent_city:
        display_name = kreis_name
        prefix = "Kreisfreie Stadt "
        if display_name.casefold().startswith(prefix.casefold()):
            display_name = display_name[len(prefix):]
        kreis_type = "Kreisfreie Stadt"
    else:
        display_name = kreis_name
        kreis_type = "Landkreis"

    normalized_properties = {
        "ags_kreis": ags_kreis,
        "ags_ba_candidate": ags_ba_candidate,
        "kreis_name": display_name,
        "kreis_type": kreis_type,
        "bundesland_code": HESSEN_CODE,
        "source": SOURCE_NAME,
        "source_layer": SOURCE_LAYER,
        "reference_date": REFERENCE_DATE,
        "source_kreis_nr": kreis_nr,
        "source_kreis_name": kreis_name,
        "source_erzeugt_am": properties.get("ERZEUGT_AM"),
    }

    return {
        "type": "Feature",
        "properties": normalized_properties,
        "geometry": geometry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Met à jour les géométries de Hesse dans le GeoJSON national."
    )
    parser.add_argument("--national-input", type=Path, default=DEFAULT_NATIONAL_INPUT)
    parser.add_argument("--hessen-input", type=Path, default=DEFAULT_HESSEN_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    print("=== MISE À JOUR GÉOGRAPHIQUE DE HESSE ===")

    try:
        national = load_geojson(args.national_input)
        hessen_source = load_geojson(args.hessen_input)

        national_features = national["features"]
        hessen_source_features = hessen_source["features"]

        # Retirer uniquement les anciennes géométries de Hesse.
        old_hessen = [
            feature
            for feature in national_features
            if (feature.get("properties") or {}).get("bundesland_code") == HESSEN_CODE
        ]
        other_states = [
            feature
            for feature in national_features
            if (feature.get("properties") or {}).get("bundesland_code") != HESSEN_CODE
        ]

        if not old_hessen:
            raise ValueError(
                "Aucune feature de Hesse trouvée dans le GeoJSON national. "
                "Vérifie la propriété bundesland_code."
            )

        print(f"Features nationales initiales : {len(national_features)}")
        print(f"Anciennes features de Hesse   : {len(old_hessen)}")
        print(f"Features des autres Länder    : {len(other_states)}")
        print(f"Features de la source Hesse   : {len(hessen_source_features)}")

        # Transformer les 27 districts de la source officielle.
        new_hessen = [
            transform_hessen_feature(feature)
            for feature in hessen_source_features
        ]

        # Construire le GeoJSON final sans toucher à l'original.
        final_features = other_states + new_hessen

        # Contrôles des identifiants.
        ags_codes = [
            str((feature.get("properties") or {}).get("ags_kreis", ""))
            for feature in final_features
        ]
        counts = Counter(ags_codes)
        duplicate_ags = sorted(
            code for code, count in counts.items() if code and count > 1
        )
        missing_ags = [
            index
            for index, feature in enumerate(final_features)
            if not (feature.get("properties") or {}).get("ags_kreis")
        ]
        missing_geometry = [
            index
            for index, feature in enumerate(final_features)
            if not feature.get("geometry")
        ]

        hessen_codes = {
            feature["properties"]["ags_kreis"]: feature["properties"]
            for feature in new_hessen
        }

        required_codes = {"06415", "06435"}
        missing_required_codes = sorted(required_codes - set(hessen_codes))

        hanau = hessen_codes.get("06415")
        main_kinzig = hessen_codes.get("06435")

        # Contrôle facultatif de validité topologique si Shapely est installé.
        invalid_geometries = []
        try:
            from shapely.geometry import shape

            for feature in final_features:
                properties = feature.get("properties") or {}
                ags = properties.get("ags_kreis")
                geometry = feature.get("geometry")

                if geometry:
                    geom = shape(geometry)
                    if geom.is_empty or not geom.is_valid:
                        invalid_geometries.append({
                            "ags_kreis": ags,
                            "reason": "empty" if geom.is_empty else "invalid",
                        })
        except ImportError:
            print(
                "AVERTISSEMENT : Shapely n'est pas installé ; "
                "le contrôle topologique n'a pas été effectué."
            )

        # Un contrôle d'identité ne garantit pas la qualité géographique.
        # Ne pas écrire le résultat si les contrôles structurels échouent.
        errors = []
        if duplicate_ags:
            errors.append(f"AGS dupliqués : {duplicate_ags}")
        if missing_ags:
            errors.append(f"Features sans AGS : {len(missing_ags)}")
        if missing_geometry:
            errors.append(f"Features sans géométrie : {len(missing_geometry)}")
        if missing_required_codes:
            errors.append(f"Codes attendus absents : {missing_required_codes}")
        if invalid_geometries:
            errors.append(f"Géométries invalides : {len(invalid_geometries)}")

        final_geojson = {
            "type": "FeatureCollection",
            "name": "germany_kreise_2026",
            "crs": national.get("crs"),
            "features": final_features,
        }

        report = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "national_input": str(args.national_input),
            "hessen_input": str(args.hessen_input),
            "output": str(args.output),
            "reference_date_hessen": REFERENCE_DATE,
            "source_layer": SOURCE_LAYER,
            "license": "Datenlizenz Deutschland – Zero 2.0",
            "initial_national_features": len(national_features),
            "old_hessen_features_removed": len(old_hessen),
            "new_hessen_features_added": len(new_hessen),
            "other_states_features_preserved": len(other_states),
            "final_features": len(final_features),
            "unique_ags": len(set(ags_codes)),
            "duplicate_ags": duplicate_ags,
            "missing_ags_count": len(missing_ags),
            "missing_geometry_count": len(missing_geometry),
            "invalid_geometries": invalid_geometries,
            "hanau": hanau,
            "main_kinzig": main_kinzig,
            "errors": errors,
            "status": "FAILED" if errors else "PASSED",
        }

        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)

        if errors:
            print("\nÉCHEC DES CONTRÔLES :")
            for error in errors:
                print(f" - {error}")
            print(f"Rapport : {args.report}")
            return 1

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as file:
            json.dump(final_geojson, file, ensure_ascii=False)

        print("\n=== RÉSULTAT ===")
        print(f"Features finales             : {len(final_features)}")
        print(f"AGS uniques                  : {len(set(ags_codes))}")
        print(f"Hanau                        : {hanau['ags_kreis']} — {hanau['kreis_name']}")
        print(
            f"Main-Kinzig-Kreis            : "
            f"{main_kinzig['ags_kreis']} — {main_kinzig['kreis_name']}"
        )
        print(f"Fichier créé                 : {args.output}")
        print(f"Rapport QC                   : {args.report}")
        print("Statut QC                    : PASSED")

        return 0

    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
