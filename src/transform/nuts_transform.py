import argparse
from pathlib import Path
import pandas as pd


def extract_nuts_germany(input_file: str, output_file: str):

    print("=== Extraction du référentiel NUTS Allemagne ===")

    # ---------------------------------------------------------
    # 1. Lecture de la feuille DE
    # ---------------------------------------------------------
    print(f"Lecture du fichier : {input_file}")

    df = pd.read_excel(
        input_file,
        sheet_name="DE"
    )

    print(f"Lignes originales : {len(df)}")

    # ---------------------------------------------------------
    # 2. Vérification des colonnes nécessaires
    # ---------------------------------------------------------
    required_columns = [
        "NUTS3",
        "LAU NAME NATIONAL",
        "LAU NAME LATIN"
    ]

    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Colonnes absentes de la feuille DE : {missing_columns}"
        )

    # ---------------------------------------------------------
    # 3. Nettoyage
    # ---------------------------------------------------------
    df["NUTS3"] = (
        df["NUTS3"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    df["LAU NAME NATIONAL"] = (
        df["LAU NAME NATIONAL"]
        .astype("string")
        .str.strip()
    )

    df["LAU NAME LATIN"] = (
        df["LAU NAME LATIN"]
        .astype("string")
        .str.strip()
    )

    # Garder uniquement les NUTS3 allemands
    df = df[
        df["NUTS3"].str.match(
            r"^DE[A-Z0-9]{3}$",
            na=False
        )
    ].copy()

    print(f"Lignes allemandes : {len(df)}")

    # ---------------------------------------------------------
    # 4. Construire la liste des NUTS3
    # ---------------------------------------------------------
    nuts3_df = (
        df[
            [
                "NUTS3",
                "LAU NAME NATIONAL",
                "LAU NAME LATIN"
            ]
        ]
        .dropna(subset=["NUTS3"])
        .drop_duplicates()
    )

    # ---------------------------------------------------------
    # 5. Agréger les noms LAU par NUTS3
    # ---------------------------------------------------------
    names = (
        nuts3_df
        .groupby("NUTS3")
        .agg(
            nuts3_lau_names_national=(
                "LAU NAME NATIONAL",
                lambda x: " | ".join(
                    sorted(
                        set(
                            str(v)
                            for v in x.dropna()
                            if str(v).strip()
                        )
                    )
                )
            ),
            nuts3_lau_names_latin=(
                "LAU NAME LATIN",
                lambda x: " | ".join(
                    sorted(
                        set(
                            str(v)
                            for v in x.dropna()
                            if str(v).strip()
                        )
                    )
                )
            )
        )
        .reset_index()
    )

    print(f"NUTS3 uniques trouvés : {len(names)}")

    # ---------------------------------------------------------
    # 6. Construire la hiérarchie NUTS
    # ---------------------------------------------------------
    records = []

    for code in sorted(names["NUTS3"]):

        # Exemple :
        #
        # DE1   → NUTS1
        # DE11  → NUTS2
        # DE111 → NUTS3

        nuts1 = code[:3]
        nuts2 = code[:4]

        # -------------------------------
        # NUTS 1
        # -------------------------------
        records.append({
            "nuts_code": nuts1,
            "nuts_level": 1,
            "country_code": "DE",
            "parent_code": None,
            "nuts3_lau_names_national": None,
            "nuts3_lau_names_latin": None,
            "reference_year": 2024,
            "source_system": "EUROSTAT",
            "source_file": Path(input_file).name
        })

        # -------------------------------
        # NUTS 2
        # -------------------------------
        records.append({
            "nuts_code": nuts2,
            "nuts_level": 2,
            "country_code": "DE",
            "parent_code": nuts1,
            "nuts3_lau_names_national": None,
            "nuts3_lau_names_latin": None,
            "reference_year": 2024,
            "source_system": "EUROSTAT",
            "source_file": Path(input_file).name
        })

        # -------------------------------
        # NUTS 3
        # -------------------------------
        row = names[
            names["NUTS3"] == code
        ].iloc[0]

        records.append({
            "nuts_code": code,
            "nuts_level": 3,
            "country_code": "DE",
            "parent_code": nuts2,
            "nuts3_lau_names_national": row[
                "nuts3_lau_names_national"
            ],
            "nuts3_lau_names_latin": row[
                "nuts3_lau_names_latin"
            ],
            "reference_year": 2024,
            "source_system": "EUROSTAT",
            "source_file": Path(input_file).name
        })

    # ---------------------------------------------------------
    # 7. DataFrame final
    # ---------------------------------------------------------
    result = pd.DataFrame(records)

    result = result.drop_duplicates(
        subset=["nuts_code"]
    )

    result = result.sort_values(
        by=["nuts_level", "nuts_code"]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # 8. Contrôles qualité
    # ---------------------------------------------------------
    print("\n=== Contrôle qualité ===")

    print(f"Total codes NUTS : {len(result)}")

    for level in [1, 2, 3]:
        count = (
            result["nuts_level"] == level
        ).sum()

        print(
            f"NUTS {level} : {count}"
        )

    # Pays
    invalid_country = result[
        result["country_code"] != "DE"
    ]

    if not invalid_country.empty:
        raise ValueError(
            "Des codes appartenant à un autre pays ont été trouvés."
        )

    # Doublons
    duplicates = result[
        result["nuts_code"].duplicated(
            keep=False
        )
    ]

    if not duplicates.empty:
        raise ValueError(
            "Des codes NUTS dupliqués ont été trouvés."
        )

    print("Doublons : 0")

    # Hiérarchie
    invalid_parent = result[
        (result["nuts_level"] > 1)
        &
        (~result["parent_code"].isin(
            result["nuts_code"]
        ))
    ]

    if not invalid_parent.empty:
        raise ValueError(
            "Certains parent_code ne correspondent "
            "à aucun code NUTS."
        )

    print("Hiérarchie : OK")

    # Vérification NUTS3
    nuts3_count = (
        result["nuts_level"] == 3
    ).sum()

    if nuts3_count != 400:
        raise ValueError(
            f"Nombre de NUTS3 inattendu : "
            f"{nuts3_count}"
        )

    print("NUTS3 : 400")

    # ---------------------------------------------------------
    # 9. Création du dossier de sortie
    # ---------------------------------------------------------
    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # ---------------------------------------------------------
    # 10. Export CSV
    # ---------------------------------------------------------
    result.to_csv(
        output_path,
        sep=";",
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"\nCSV créé : {output_path}"
    )

    print("\n=== Résumé ===")

    print(
        result[
            [
                "nuts_code",
                "nuts_level",
                "country_code",
                "parent_code",
                "nuts3_lau_names_national"
            ]
        ]
        .head(20)
        .to_string(index=False)
    )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Extraction du référentiel NUTS "
            "Allemagne depuis Eurostat"
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
        help="Fichier CSV de sortie"
    )

    args = parser.parse_args()

    extract_nuts_germany(
        args.input,
        args.output
    )


if __name__ == "__main__":
    main()