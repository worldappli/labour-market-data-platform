from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT = PROJECT_ROOT / "data" / "processed" / "ba_arbeitslosigkeit.csv"
OUTPUT = PROJECT_ROOT / "data" / "processed" / "ba_duplicates.csv"

print(f"Fichier d'entrée : {INPUT}")

df = pd.read_csv(
    INPUT,
    dtype=str,
    sep=";"
)

print(f"Nombre total de lignes : {len(df)}")

key = ["ags", "period"]

duplicates = df[df.duplicated(key, keep=False)].copy()

print(f"Nombre de lignes en doublon : {len(duplicates)}")
print(
    f"Nombre de clés AGS + période concernées : "
    f"{duplicates[key].drop_duplicates().shape[0]}"
)

# Doublons strictement identiques
identical = (
    duplicates
    .groupby(key, dropna=False)
    .filter(lambda g: len(g.drop_duplicates()) == 1)
)

# Doublons avec valeurs différentes
different = (
    duplicates
    .groupby(key, dropna=False)
    .filter(lambda g: len(g.drop_duplicates()) > 1)
)

print("\n=== DOUBLONS IDENTIQUES ===")
print(f"Lignes : {len(identical)}")

print("\n=== DOUBLONS AVEC VALEURS DIFFERENTES ===")
print(f"Lignes : {len(different)}")

if len(different) > 0:
    print("\nExemples :")
    print(
        different[
            [
                "ags",
                "ba_id",
                "kreis",
                "period",
                "arbeitslose",
                "unterbeschaeftigung"
            ]
        ]
        .sort_values(key)
        .head(30)
        .to_string(index=False)
    )

duplicates.to_csv(
    OUTPUT,
    index=False,
    sep=";",
    encoding="utf-8-sig"
)

print(f"\nRésultat : {OUTPUT}")