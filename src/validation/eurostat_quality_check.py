#!/usr/bin/env python3
"""Contrôle qualité non destructif du CSV Eurostat Allemagne."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

KEY_COLUMNS = ["geo", "time", "freq", "isced11", "sex", "age", "unit"]
REQUIRED_COLUMNS = [
    "geo", "region", "time", "freq", "isced11",
    "sex", "age", "unit", "value", "status"
]


def main():
    parser = argparse.ArgumentParser(description="Contrôle qualité du CSV Eurostat.")
    parser.add_argument("--input", required=True, help="Chemin du CSV à contrôler")
    parser.add_argument(
        "--report", required=True, help="Chemin du rapport JSON de contrôle"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    report_path = Path(args.report)

    if not input_path.is_file():
        raise FileNotFoundError(f"CSV introuvable : {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        headers = reader.fieldnames or []
        rows = list(reader)

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing_columns:
        raise ValueError(f"Colonnes obligatoires absentes : {missing_columns}")

    key_counts = Counter(
        tuple((row.get(col) or "").strip() for col in KEY_COLUMNS)
        for row in rows
    )
    duplicate_keys = [
        {"key": list(key), "count": count}
        for key, count in key_counts.items()
        if count > 1
    ]

    blank_by_column = {
        col: sum(1 for row in rows if not (row.get(col) or "").strip())
        for col in headers
    }

    invalid_values = []
    out_of_range = []
    numeric_values = []
    for line_number, row in enumerate(rows, start=2):
        raw = (row.get("value") or "").strip()
        try:
            value = float(raw)
            numeric_values.append(value)
            if not 0 <= value <= 100:
                out_of_range.append({"line": line_number, "value": raw})
        except ValueError:
            invalid_values.append({"line": line_number, "value": raw})

    geos = sorted({(r.get("geo") or "").strip() for r in rows})
    years = sorted({(r.get("time") or "").strip() for r in rows if r.get("time")})

    report = {
        "file": str(input_path),
        "row_count": len(rows),
        "columns": headers,
        "missing_required_columns": missing_columns,
        "duplicate_key_count": len(duplicate_keys),
        "duplicate_keys_sample": duplicate_keys[:100],
        "blank_by_column": blank_by_column,
        "invalid_numeric_value_count": len(invalid_values),
        "invalid_numeric_value_sample": invalid_values[:100],
        "values_outside_0_100_count": len(out_of_range),
        "values_outside_0_100_sample": out_of_range[:100],
        "value_min": min(numeric_values) if numeric_values else None,
        "value_max": max(numeric_values) if numeric_values else None,
        "geography_count": len(geos),
        "geographies_not_starting_DE": [g for g in geos if not g.startswith("DE")],
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== Contrôle qualité Eurostat ===")
    print(f"Lignes : {len(rows):,}")
    print(f"Codes géographiques : {len(geos)}")
    print(f"Période : {report['year_min']}–{report['year_max']}")
    print(f"Clés dupliquées : {len(duplicate_keys)}")
    print(f"Valeurs numériques invalides : {len(invalid_values)}")
    print(f"Valeurs hors intervalle 0–100 : {len(out_of_range)}")
    print(f"Rapport JSON : {report_path}")
    print("Aucune donnée du CSV n'a été modifiée.")


if __name__ == "__main__":
    main()
