"""
Ingestion des données « Eckwerte Arbeitslosigkeit » de la Bundesagentur für Arbeit.
La liste officielle des territoires est chargée depuis kreise_ba.csv (même dossier).

Le CSV de référence contient :
- name : nom officiel utilisé comme paramètre API « Kreis »
- ba_id : identifiant de territoire BA
- ags : code territorial (BA_SCHL)

La réponse est archivée sans transformation dans data/raw/ba_arbeitslosigkeit/.
"""

import csv
import re
import time
from pathlib import Path

import requests

BASE_URL = (
    "https://statistik-dr.arbeitsagentur.de/bifrontend/bids-api/ct/v1/"
    "tableFetch/csv/EckwerteZeitreiheALO"
)
BASE_DIR = Path(__file__).resolve().parent
KREISE_CSV = BASE_DIR.parent.parent / "data" / "reference" / "kreise_ba.csv"
OUTPUT_DIR = BASE_DIR.parent.parent / "data" / "raw" / "ba_arbeitslosigkeit"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ThesisDataWarehouse/1.0)"
}
REQUEST_DELAY_SECONDS = 1.0


def load_kreise(csv_path: Path = KREISE_CSV) -> list[dict[str, str]]:
    """Charge la nomenclature officielle depuis le fichier CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Fichier de référence introuvable : {csv_path}. "
            "Place kreise_ba.csv à côté du script."
        )
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"name", "ba_id", "ags"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Colonnes requises : {sorted(required)}. "
                f"Colonnes trouvées : {reader.fieldnames}"
            )
        return [
            row for row in reader
            if row.get("name", "").strip()
        ]


def safe_filename(value: str) -> str:
    """Produit un nom de fichier stable sans modifier le nom envoyé à l'API."""
    value = re.sub(r'[<>:"/\\|?*]', "_", value.strip())
    value = re.sub(r"\s+", "_", value)
    return value


def fetch_kreis(kreis_name: str) -> bytes:
    """Récupère la réponse brute de l'API pour un territoire."""
    response = requests.get(
        BASE_URL,
        params={"Kreis": kreis_name},
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    body = response.content

    # L'API peut renvoyer une erreur JSON avec un statut HTTP 200.
    if body.lstrip().startswith(b'{"err"'):
        raise ValueError(
            f"Réponse d'erreur de l'API pour {kreis_name!r}: "
            f"{body[:500].decode('utf-8', errors='replace')}"
        )
    return body


def save_raw(kreis: dict[str, str], content: bytes) -> Path:
    """Archive les octets reçus sans parsing ni transformation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_filename(kreis['name'])}_{kreis['ags']}.csv"
    filepath = OUTPUT_DIR / filename
    filepath.write_bytes(content)
    return filepath


def main() -> None:
    kreise = load_kreise()
    results = {"ok": [], "erreurs": []}
    print(f"Territoires chargés depuis {KREISE_CSV.name} : {len(kreise)}")

    for index, kreis in enumerate(kreise, start=1):
        name = kreis["name"].strip()
        try:
            content = fetch_kreis(name)
            path = save_raw(kreis, content)
            print(f"[{index}/{len(kreise)}] [OK] {name} -> {path}")
            results["ok"].append(name)
        except (requests.RequestException, ValueError) as exc:
            print(f"[{index}/{len(kreise)}] [ERREUR] {name}: {exc}")
            results["erreurs"].append(name)

        if index < len(kreise):
            time.sleep(REQUEST_DELAY_SECONDS)

    print(
        f"\nTerminé : {len(results['ok'])} OK, "
        f"{len(results['erreurs'])} erreurs."
    )
    if results["erreurs"]:
        print("Territoires en erreur :", results["erreurs"])


if __name__ == "__main__":
    main()
