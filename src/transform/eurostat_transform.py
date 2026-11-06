#!/usr/bin/env python3
"""
Transforme un fichier JSON-Stat Eurostat en CSV contenant uniquement
les observations géographiques allemandes (codes commençant par DE).

Exemple :
python scr/transform/eurostat_transform.py \
  --input data/raw/eurostat/lfst_r_lfu3rt_20260929T182927Z.json \
  --output data/processed/eurostat_allemagne.csv

Le CSV est écrit en UTF-8 avec BOM et séparateur point-virgule (;).
Les observations absentes du champ "value" du JSON-Stat ne sont pas exportées.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OUTPUT_COLUMNS = [
    "geo",
    "region",
    "time",
    "freq",
    "isced11",
    "sex",
    "age",
    "unit",
    "value",
    "status",
]


def get_categories(dimension: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Retourne les codes de catégories dans leur ordre JSON-Stat et leurs libellés."""
    category = dimension.get("category", {})
    index = category.get("index", {})
    labels = category.get("label", {})

    if isinstance(index, dict):
        codes = [code for code, _ in sorted(index.items(), key=lambda item: item[1])]
    elif isinstance(index, list):
        codes = index
    else:
        codes = list(labels.keys())

    return codes, labels


def decode_position(flat_index: int, sizes: list[int]) -> list[int]:
    """Décode un index aplati JSON-Stat en positions de dimensions (ordre row-major)."""
    positions: list[int] = []
    remainder = flat_index

    for i, size in enumerate(sizes):
        stride = 1
        for following_size in sizes[i + 1 :]:
            stride *= following_size

        positions.append(remainder // stride)
        remainder %= stride

    return positions


def transform(input_path: Path, output_path: Path) -> int:
    if not input_path.is_file():
        raise FileNotFoundError(f"Fichier JSON introuvable : {input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    dimension_ids = dataset["id"]
    sizes = dataset["size"]
    dimensions = dataset["dimension"]
    values = dataset.get("value", {})
    statuses = dataset.get("status", {})

    if len(dimension_ids) != len(sizes):
        raise ValueError("Le nombre de dimensions ne correspond pas à 'size'.")

    category_codes: dict[str, list[str]] = {}
    category_labels: dict[str, dict[str, str]] = {}

    for dimension_id in dimension_ids:
        codes, labels = get_categories(dimensions[dimension_id])
        category_codes[dimension_id] = codes
        category_labels[dimension_id] = labels

    if "geo" not in dimension_ids or "time" not in dimension_ids:
        raise ValueError("Le JSON-Stat doit contenir les dimensions 'geo' et 'time'.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    geographies: set[str] = set()

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_COLUMNS,
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()

        for flat_key, value in values.items():
            positions = decode_position(int(flat_key), sizes)

            row = {
                dimension_ids[i]: category_codes[dimension_ids[i]][positions[i]]
                for i in range(len(dimension_ids))
            }

            geo = str(row.get("geo", ""))
            if not geo.startswith("DE"):
                continue

            row["region"] = category_labels["geo"].get(geo, geo)
            row["value"] = value
            row["status"] = statuses.get(str(flat_key), "")

            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})
            count += 1
            geographies.add(geo)

    print(f"Fichier source : {input_path}")
    print(f"Fichier CSV   : {output_path}")
    print(f"Observations exportées : {count:,}")
    print(f"Codes géographiques allemands : {len(geographies)}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transforme le JSON-Stat Eurostat en CSV pour les géographies allemandes."
    )
    parser.add_argument("--input", required=True, help="Chemin du JSON Eurostat brut")
    parser.add_argument("--output", required=True, help="Chemin du CSV de sortie")
    args = parser.parse_args()

    transform(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
