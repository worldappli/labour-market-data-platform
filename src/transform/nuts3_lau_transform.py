import argparse
from pathlib import Path
import pandas as pd


def extract_nuts3_lau(input_file: str, output_file: str):

    print("=== Extraction NUTS3 ↔ LAU Allemagne ===")

    # ---------------------------------------------------------
    # 1. Lecture de la feuille DE
    # ---------------------------------------------------------
    print(f"Lecture : {input_file}")

    df = pd.read_excel(
        input_file,
        sheet_name="DE"
    )

    print(f"Lignes originales : {len(df)}")

    # ---------------------------------------------------------
    # 2. Vérification des colonnes
    # ---------------------------------------------------------
    required_columns = [
        "NUTS3",
        "LAU CODE",
        "LAU NAME NATIONAL",
        "LAU NAME LATIN"
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Colonnes absentes : {missing}"
        )

    # ---------------------------------------------------------
    # 3. Sélection des colonnes
    # ---------------------------------------------------------
    result = df[
        [
            "NUTS3",
            "LAU CODE",
            "LAU NAME NATIONAL",
            "LAU NAME LATIN"
        ]
    ].copy()

    # ---------------------------------------------------------
    # 4. Nettoyage
    # ---------------------------------------------------------
    result["NUTS3"] = (
        result["NUTS3"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    result["LAU CODE"] = (
        result["LAU CODE"]
        .astype("string")
        .str.strip()
    )

    result["LAU NAME NATIONAL"] = (
        result["LAU NAME NATIONAL"]
        .astype("string")
        .str.strip()
    )

    result["LAU NAME LATIN"] = (
        result["LAU NAME LATIN"]
        .astype("string")
        .str.strip()
    )

    # ---------------------------------------------------------
    # 5. Garder uniquement les NUTS3 allemands
    # ---------------------------------------------------------
    result = result[
        result["NUTS3"].str.match(
            r"^DE[A-Z0-9]{3}$",
            na=False
        )
    ].copy()

    # ---------------------------------------------------------
    # 6. Supprimer les lignes sans LAU
    # ---------------------------------------------------------
    result = result[
        result["LAU CODE"].notna()
        & (result["LAU CODE"] != "")
    ].copy()

    # ---------------------------------------------------------
    # 7. Renommer les colonnes
    # ---------------------------------------------------------
    result = result.rename(
        columns={
            "NUTS3": "nuts3_code",
            "LAU CODE": "lau_code",
            "LAU NAME NATIONAL": "lau_name_national",
            "LAU NAME LATIN": "lau_name_latin"
        }
    )

    # ---------------------------------------------------------
    # 8. Métadonnées
    # ---------------------------------------------------------
    result["reference_year"] = 2024
    result["source_system"] = "EUROSTAT"
    result["source_file"] = Path(input_file).name

    # ---------------------------------------------------------
    # 9. Déduplication
    # ---------------------------------------------------------
    result = result.drop_duplicates(
        subset=[
            "nuts3_code",
            "lau_code"
        ]
    )

    # ---------------------------------------------------------
    # 10. Tri
    # ---------------------------------------------------------
    result = result.sort_values(
        by=[
            "nuts3_code",
            "lau_code"
        ]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # 11. Contrôles qualité
    # ---------------------------------------------------------
    print("\n=== Contrôle qualité ===")

    print(
        f"Relations NUTS3 ↔ LAU : {len(result)}"
    )

    print(
        f"NUTS3 uniques : "
        f"{result['nuts3_code'].nunique()}"
    )

    print(
        f"LAU uniques : "
        f"{result['lau_code'].nunique()}"
    )

    # Doublons
    duplicates = result[
        result.duplicated(
            subset=["nuts3_code", "lau_code"],
            keep=False
        )
    ]

    print(
        f"Doublons NUTS3 + LAU : "
        f"{len(duplicates)}"
    )

    if not duplicates.empty:
        raise ValueError(
            "Des doublons NUTS3 + LAU ont été détectés."
        )

    # NUTS3 invalides
    invalid_nuts3 = result[
        ~result["nuts3_code"].str.match(
            r"^DE[A-Z0-9]{3}$"
        )
    ]

    if not invalid_nuts3.empty:
        raise ValueError(
            "Des codes NUTS3 invalides ont été détectés."
        )

    print("Codes NUTS3 : OK")

    # ---------------------------------------------------------
    # 12. Vérifier combien de LAU sont associés à chaque NUTS3
    # ---------------------------------------------------------
    stats = (
        result
        .groupby("nuts3_code")
        .size()
        .describe()
    )

    print("\nNombre de LAU par NUTS3 :")
    print(stats)

    # ---------------------------------------------------------
    # 13. Export
    # ---------------------------------------------------------
    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_csv(
        output_path,
        sep=";",
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"\nCSV créé : {output_path}"
    )

    print("\n=== Exemple ===")
    print(
        result.head(10).to_string(
            index=False
        )
    )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Extraction de la relation "
            "NUTS3 ↔ LAU pour l'Allemagne"
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Fichier Excel NUTS"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="CSV de sortie"
    )

    args = parser.parse_args()

    extract_nuts3_lau(
        args.input,
        args.output
    )


if __name__ == "__main__":
    main()