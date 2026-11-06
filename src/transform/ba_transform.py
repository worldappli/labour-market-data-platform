from pathlib import Path
import argparse
import csv
import re


MONTHS = {
    "Januar": "01",
    "Februar": "02",
    "März": "03",
    "April": "04",
    "Mai": "05",
    "Juni": "06",
    "Juli": "07",
    "August": "08",
    "September": "09",
    "Oktober": "10",
    "November": "11",
    "Dezember": "12",
}


OUTPUT_COLUMNS = [
    "ags",
    "ba_id",
    "kreis",
    "period",
    "arbeitslose",
    "unterbeschaeftigung",
]


def normalize_name(value: str) -> str:
    """
    Normalise un nom de Kreis pour faciliter le mapping.
    """
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def load_kreise(reference_path: Path) -> dict[str, dict[str, str]]:
    """
    Charge le fichier de référence kreise_ba.csv.

    Colonnes attendues :
        name;ba_id;ags
    """

    reference = {}

    with reference_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file, delimiter=";")

        required_columns = {"name", "ba_id", "ags"}

        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(
                "Colonnes obligatoires absentes dans kreise_ba.csv. "
                f"Colonnes attendues : {required_columns}"
            )

        for row in reader:
            name = row["name"].strip()
            ba_id = row["ba_id"].strip()
            ags = row["ags"].strip()

            if not name or not ags:
                continue

            key = normalize_name(name)

            if key in reference:
                raise ValueError(
                    f"Doublon dans kreise_ba.csv pour le Kreis : {name}"
                )

            reference[key] = {
                "name": name,
                "ba_id": ba_id,
                "ags": ags,
            }

    return reference


def extract_file_kreis(
    path: Path,
    lines: list[list[str]],
) -> str:
    """
    Extrait le nom du Kreis depuis les métadonnées du fichier BA.

    Exemple :
        Kreis:;Ahrweiler
    """

    for row in lines:
        if not row:
            continue

        first_cell = row[0].strip().lower()

        if first_cell == "kreis:" and len(row) > 1:
            return row[1].strip()

    raise ValueError(
        f"Nom du Kreis introuvable dans {path.name}"
    )


def parse_year_from_metadata(
    lines: list[list[str]],
) -> int | None:
    """
    Recherche une année dans les métadonnées du fichier.

    Exemple :
        Berichtszeitraum:;Januar 2007 bis August 2026
    """

    for row in lines:
        if not row:
            continue

        text = " ".join(cell.strip() for cell in row)

        if "Berichtszeitraum" in text:
            years = re.findall(r"\b(20\d{2})\b", text)

            if years:
                return int(years[-1])

    return None


def parse_month_and_year(
    raw_period: str,
    current_year: int | None,
    previous_month: int | None,
) -> tuple[str, int, int]:

    value = raw_period.strip()

    year_match = re.search(r"\b(20\d{2})\b", value)

    month_name = None

    for month in MONTHS:
        if month.lower() in value.lower():
            month_name = month
            break

    if month_name is None:
        raise ValueError(
            f"Mois BA non reconnu : {raw_period!r}"
        )

    month = int(MONTHS[month_name])

    if year_match:
        year = int(year_match.group(1))

    elif current_year is not None:
        year = current_year

        # Les fichiers BA sont généralement dans l'ordre
        # décroissant : August, July, ..., January,
        # December, November, ...
        if (
            previous_month is not None
            and month > previous_month
        ):
            year -= 1

    else:
        raise ValueError(
            f"Année impossible à déterminer pour la période : "
            f"{raw_period!r}"
        )

    return f"{year:04d}-{month:02d}", year, month


def normalize_value(value: str) -> str:
    """
    Normalise une valeur BA.

    x / vide -> vide
    nombres -> entier sous forme texte
    """

    value = value.strip()

    if not value or value.lower() == "x":
        return ""

    value = value.replace(" ", "")

    if not re.fullmatch(r"\d+", value):
        raise ValueError(
            f"Valeur numérique BA inattendue : {value!r}"
        )

    return value


def read_ba_file(
    path: Path,
    kreise_reference: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """
    Transforme un fichier BA en lignes normalisées.
    """

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        lines = list(
            csv.reader(
                file,
                delimiter=";",
            )
        )

    if not lines:
        raise ValueError("Fichier vide")

    # ---------------------------------------------------------
    # Identification du Kreis
    # ---------------------------------------------------------

    kreis = extract_file_kreis(
        path,
        lines,
    )

    reference = kreise_reference.get(
        normalize_name(kreis)
    )

    if reference is None:
        raise ValueError(
            f"Kreis '{kreis}' absent de kreise_ba.csv "
            f"(fichier : {path.name})"
        )

    # ---------------------------------------------------------
    # Recherche de l'en-tête des observations
    # ---------------------------------------------------------

    header_index = None

    for index, row in enumerate(lines):

        normalized = [
            cell.strip()
            for cell in row
        ]

        if (
            "Berichtsmonat" in normalized
            and "Arbeitslose" in normalized
        ):
            header_index = index
            break

    if header_index is None:
        raise ValueError(
            "En-tête des observations introuvable "
            "(Berichtsmonat / Arbeitslose)"
        )

    header = [
        cell.strip()
        for cell in lines[header_index]
    ]

    # ---------------------------------------------------------
    # Identification des colonnes
    # ---------------------------------------------------------

    try:
        month_index = header.index(
            "Berichtsmonat"
        )

        arbeitslose_index = header.index(
            "Arbeitslose"
        )

    except ValueError as exc:

        raise ValueError(
            f"Colonnes BA obligatoires absentes "
            f"dans {path.name}"
        ) from exc

    unter_index = None

    if "Unterbeschäftigung" in header:
        unter_index = header.index(
            "Unterbeschäftigung"
        )

    # ---------------------------------------------------------
    # Année de référence
    # ---------------------------------------------------------

    metadata_year = parse_year_from_metadata(
        lines
    )

    result = []

    current_year = metadata_year
    previous_month = None

    # ---------------------------------------------------------
    # Lecture des observations
    # ---------------------------------------------------------

    for raw_row in lines[header_index + 1:]:

        if len(raw_row) <= month_index:
            continue

        raw_period = raw_row[
            month_index
        ].strip()

        if not raw_period:
            continue

        # Ignore les lignes qui ne sont pas des observations.
        if not any(
            month.lower()
            in raw_period.lower()
            for month in MONTHS
        ):
            continue

        period, year, month = parse_month_and_year(
            raw_period,
            current_year,
            previous_month,
        )

        current_year = year
        previous_month = month

        # -----------------------------------------------------
        # Arbeitslose
        # -----------------------------------------------------

        arbeitslose_raw = (
            raw_row[arbeitslose_index]
            if arbeitslose_index < len(raw_row)
            else ""
        )

        # -----------------------------------------------------
        # Unterbeschäftigung
        # -----------------------------------------------------

        unter_raw = (
            raw_row[unter_index]
            if (
                unter_index is not None
                and unter_index < len(raw_row)
            )
            else ""
        )

        result.append(
            {
                "ags": reference["ags"],
                "ba_id": reference["ba_id"],
                "kreis": reference["name"],
                "period": period,
                "arbeitslose": normalize_value(
                    arbeitslose_raw
                ),
                "unterbeschaeftigung": normalize_value(
                    unter_raw
                ),
            }
        )

    return result


def transform(
    input_dir: Path,
    reference_path: Path,
    output_path: Path,
) -> int:

    files = sorted(
        input_dir.glob("*.csv")
    )

    if not files:
        raise FileNotFoundError(
            f"Aucun fichier CSV trouvé dans : "
            f"{input_dir}"
        )

    # ---------------------------------------------------------
    # Chargement de la référence
    # ---------------------------------------------------------

    kreise_reference = load_kreise(
        reference_path
    )

    all_rows = []

    errors = []

    # ---------------------------------------------------------
    # Structures de contrôle des doublons
    # ---------------------------------------------------------

    # Clé :
    #     (AGS, period)
    #
    # Valeur :
    #     ligne conservée
    unique_rows = {}

    # Permet de savoir quel fichier a fourni
    # chaque observation.
    row_sources = {}

    # Doublons identiques
    duplicate_identical = []

    # Conflits
    conflicts = []

    # ---------------------------------------------------------
    # Transformation des fichiers
    # ---------------------------------------------------------

    for index, path in enumerate(
        files,
        start=1,
    ):

        try:

            rows = read_ba_file(
                path,
                kreise_reference,
            )

            accepted = 0
            duplicates = 0

            for row in rows:

                key = (
                    row["ags"],
                    row["period"],
                )

                # -------------------------------------------------
                # Nouvelle observation
                # -------------------------------------------------

                if key not in unique_rows:

                    unique_rows[key] = row
                    row_sources[key] = path.name

                    accepted += 1

                    continue

                # -------------------------------------------------
                # Observation déjà rencontrée
                # -------------------------------------------------

                existing = unique_rows[key]

                source_file = row_sources[key]

                # -------------------------------------------------
                # Vérification des valeurs
                # -------------------------------------------------

                same_values = (
                    existing["arbeitslose"]
                    == row["arbeitslose"]
                    and
                    existing["unterbeschaeftigung"]
                    == row["unterbeschaeftigung"]
                )

                if same_values:

                    duplicate_identical.append(
                        {
                            "ags": row["ags"],
                            "kreis": row["kreis"],
                            "period": row["period"],
                            "source_file_1": source_file,
                            "source_file_2": path.name,
                        }
                    )

                    duplicates += 1

                else:

                    conflicts.append(
                        {
                            "ags": row["ags"],
                            "kreis": row["kreis"],
                            "period": row["period"],
                            "source_file_1": source_file,
                            "source_file_2": path.name,
                            "arbeitslose_1": existing[
                                "arbeitslose"
                            ],
                            "arbeitslose_2": row[
                                "arbeitslose"
                            ],
                            "unterbeschaeftigung_1": existing[
                                "unterbeschaeftigung"
                            ],
                            "unterbeschaeftigung_2": row[
                                "unterbeschaeftigung"
                            ],
                        }
                    )

            print(
                f"[{index}/{len(files)}] OK - "
                f"{path.name} : "
                f"{len(rows)} observations "
                f"({accepted} nouvelles, "
                f"{duplicates} doublons)"
            )

        except (
            OSError,
            ValueError,
            KeyError,
        ) as exc:

            errors.append(
                f"{path.name}: {exc}"
            )

            print(
                f"[{index}/{len(files)}] ERREUR - "
                f"{path.name}: {exc}"
            )

    # ---------------------------------------------------------
    # Construction finale
    # ---------------------------------------------------------

    all_rows = list(
        unique_rows.values()
    )

    # Tri déterministe :
    # AGS puis période
    all_rows.sort(
        key=lambda row: (
            row["ags"],
            row["period"],
        )
    )

    # ---------------------------------------------------------
    # Création du dossier de sortie
    # ---------------------------------------------------------

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Écriture du CSV final
    # ---------------------------------------------------------

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_COLUMNS,
            delimiter=";",
        )

        writer.writeheader()
        writer.writerows(all_rows)

    # ---------------------------------------------------------
    # Rapport final
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("=== Transformation BA terminée ===")
    print("=" * 60)

    print(
        f"Fichiers trouvés       : {len(files):,}"
    )

    print(
        f"Fichiers en erreur     : {len(errors):,}"
    )

    print(
        f"Observations uniques   : {len(all_rows):,}"
    )

    print(
        f"Doublons identiques    : "
        f"{len(duplicate_identical):,}"
    )

    print(
        f"Conflits détectés      : "
        f"{len(conflicts):,}"
    )

    print(
        f"Fichier de sortie      : "
        f"{output_path}"
    )

    # ---------------------------------------------------------
    # Détails des doublons
    # ---------------------------------------------------------

    if duplicate_identical:

        print()
        print(
            "=== Doublons identiques détectés ==="
        )

        # Affichage des fichiers impliqués
        duplicate_files = set()

        for duplicate in duplicate_identical:

            duplicate_files.add(
                duplicate["source_file_1"]
            )

            duplicate_files.add(
                duplicate["source_file_2"]
            )

        print(
            f"Fichiers concernés : "
            f"{len(duplicate_files)}"
        )

        for filename in sorted(
            duplicate_files
        ):
            print(
                f" - {filename}"
            )

        print(
            f"Observations dupliquées ignorées : "
            f"{len(duplicate_identical):,}"
        )

    # ---------------------------------------------------------
    # Détails des conflits
    # ---------------------------------------------------------

    if conflicts:

        print()
        print(
            "!!! CONFLITS DE DONNÉES DÉTECTÉS !!!"
        )

        for conflict in conflicts:

            print()
            print(
                f"AGS      : {conflict['ags']}"
            )

            print(
                f"Kreis    : {conflict['kreis']}"
            )

            print(
                f"Période  : {conflict['period']}"
            )

            print(
                f"Fichier 1 : "
                f"{conflict['source_file_1']}"
            )

            print(
                f"Fichier 2 : "
                f"{conflict['source_file_2']}"
            )

            print(
                "Arbeitslose : "
                f"{conflict['arbeitslose_1']} "
                "vs "
                f"{conflict['arbeitslose_2']}"
            )

            print(
                "Unterbeschäftigung : "
                f"{conflict['unterbeschaeftigung_1']} "
                "vs "
                f"{conflict['unterbeschaeftigung_2']}"
            )

        raise ValueError(
            f"{len(conflicts)} conflit(s) de données "
            "détecté(s). Le fichier final a été généré, "
            "mais les conflits doivent être analysés."
        )

    # ---------------------------------------------------------
    # Erreurs fichiers
    # ---------------------------------------------------------

    if errors:

        print()
        print(
            "=== Fichiers en erreur ==="
        )

        for error in errors:
            print(
                f" - {error}"
            )

        raise ValueError(
            f"Transformation interrompue : "
            f"{len(errors)} fichier(s) invalide(s). "
            "Les erreurs doivent être corrigées avant "
            "de poursuivre le pipeline."
        )

    print()
    print(
        "Transformation terminée avec succès."
    )

    return len(all_rows)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Consolide les fichiers CSV BA "
            "en un CSV normalisé et "
            "détecte les doublons."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Dossier contenant les CSV BA RAW"
        ),
    )

    parser.add_argument(
        "--reference",
        required=True,
        help=(
            "Fichier de référence "
            "kreise_ba.csv"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "CSV BA consolidé"
        ),
    )

    args = parser.parse_args()

    transform(
        input_dir=Path(args.input),
        reference_path=Path(args.reference),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()