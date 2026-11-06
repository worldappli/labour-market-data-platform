#!/usr/bin/env python3
import argparse, csv, json
from collections import Counter
from pathlib import Path

REQUIRED = ["ags","ba_id","kreis","period","arbeitslose","unterbeschaeftigung"]

def main():
    p = argparse.ArgumentParser(description="Contrôle qualité du CSV BA consolidé.")
    p.add_argument("--input", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()

    inp, out = Path(args.input), Path(args.report)
    if not inp.is_file():
        raise FileNotFoundError(f"CSV introuvable : {inp}")

    with inp.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter=";")
        cols = r.fieldnames or []
        rows = list(r)

    missing_cols = [c for c in REQUIRED if c not in cols]

    blanks = {c: sum(not (row.get(c) or "").strip() for row in rows) for c in cols}

    keys = Counter(((row.get("ags") or "").strip(), (row.get("period") or "").strip()) for row in rows)
    duplicates = [{"ags": k[0], "period": k[1], "count": n} for k,n in keys.items() if n > 1]

    invalid_periods = []
    invalid_numeric = []
    negative = []
    missing_values = {"arbeitslose": 0, "unterbeschaeftigung": 0}
    stats = {c: {"count": 0, "min": None, "max": None} for c in missing_values}
    inconsistencies = []

    for line, row in enumerate(rows, start=2):
        period = (row.get("period") or "").strip()
        valid_period = (
            len(period) == 7 and period[4] == "-" and
            period[:4].isdigit() and period[5:].isdigit() and
            1 <= int(period[5:]) <= 12
        )
        if not valid_period:
            invalid_periods.append({"line": line, "period": period})

        parsed = {}
        for col in missing_values:
            raw = (row.get(col) or "").strip()
            if raw == "":
                missing_values[col] += 1
                continue
            try:
                value = int(raw)
                parsed[col] = value
                s = stats[col]
                s["count"] += 1
                s["min"] = value if s["min"] is None else min(s["min"], value)
                s["max"] = value if s["max"] is None else max(s["max"], value)
                if value < 0:
                    negative.append({"line": line, "column": col, "value": value})
            except ValueError:
                invalid_numeric.append({"line": line, "column": col, "value": raw})

        if "arbeitslose" in parsed and "unterbeschaeftigung" in parsed:
            if parsed["arbeitslose"] > parsed["unterbeschaeftigung"]:
                inconsistencies.append({
                    "line": line,
                    "ags": row.get("ags",""),
                    "period": period,
                    "arbeitslose": parsed["arbeitslose"],
                    "unterbeschaeftigung": parsed["unterbeschaeftigung"]
                })

    ags = sorted({(r.get("ags") or "").strip() for r in rows if (r.get("ags") or "").strip()})
    ba_ids = sorted({(r.get("ba_id") or "").strip() for r in rows if (r.get("ba_id") or "").strip()})
    kreise = sorted({(r.get("kreis") or "").strip() for r in rows if (r.get("kreis") or "").strip()})
    periods = sorted({(r.get("period") or "").strip() for r in rows if (r.get("period") or "").strip()})

    report = {
        "file": str(inp),
        "row_count": len(rows),
        "columns": cols,
        "missing_required_columns": missing_cols,
        "blank_by_column": blanks,
        "duplicate_key_count": len(duplicates),
        "duplicate_keys_sample": duplicates[:100],
        "invalid_period_count": len(invalid_periods),
        "invalid_period_sample": invalid_periods[:100],
        "invalid_numeric_count": len(invalid_numeric),
        "invalid_numeric_sample": invalid_numeric[:100],
        "negative_value_count": len(negative),
        "negative_value_sample": negative[:100],
        "missing_values": missing_values,
        "numeric_statistics": stats,
        "ags_count": len(ags),
        "ba_id_count": len(ba_ids),
        "kreis_count": len(kreise),
        "period_count": len(periods),
        "period_min": min(periods) if periods else None,
        "period_max": max(periods) if periods else None,
        "logical_inconsistency_count": len(inconsistencies),
        "logical_inconsistency_sample": inconsistencies[:100]
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Contrôle qualité BA ===")
    print(f"Lignes : {len(rows):,}")
    print(f"Colonnes manquantes : {len(missing_cols)}")
    print(f"Territoires AGS : {len(ags)}")
    print(f"Kreise : {len(kreise)}")
    print(f"Periode : {report['period_min']} - {report['period_max']}")
    print(f"Doublons AGS + période : {len(duplicates)}")
    print(f"Périodes invalides : {len(invalid_periods)}")
    print(f"Valeurs numériques invalides : {len(invalid_numeric)}")
    print(f"Valeurs négatives : {len(negative)}")
    print(f"Valeurs manquantes - Arbeitslose : {missing_values['arbeitslose']}")
    print(f"Valeurs manquantes - Unterbeschäftigung : {missing_values['unterbeschaeftigung']}")
    print(f"Incohérences Arbeitslose > Unterbeschäftigung : {len(inconsistencies)}")
    print(f"Rapport : {out}")
    print("Aucune donnée du CSV n'a été modifiée.")

if __name__ == "__main__":
    main()
