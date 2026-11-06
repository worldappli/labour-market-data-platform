"""
Extraction des données Eurostat du chômage régional en Allemagne.

Emplacement : scr/extract/eurostat_ingest.py
Sortie : data/raw/eurostat/

Le filtre géographique inclut l'Allemagne (DE), les régions NUTS 1
(DE1...DEG) et les régions NUTS 2 (codes à 4 caractères).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

DATASET_CODE = "lfst_r_lfu3rt"
API_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "eurostat"
TIMEOUT_SECONDS = 120
LANGUAGE = "en"

# Dimensions du jeu lfst_r_lfu3rt (vérifiées sur la doc Eurostat) :
# sex : T (total), M (hommes), F (femmes)
# age : Y_GE15, Y_GE25, Y15-74, Y15-29, Y15-24, Y20-64, Y25-34, Y35-44, Y45-54, Y55-64
# Ne pas filtrer une dimension revient à demander TOUTES ses valeurs (comportement
# par défaut de l'API) — on les liste ici explicitement pour la traçabilité/doc,
# pas parce que c'était manquant.
SEX_CODES = ["T", "M", "F"]
AGE_CODES = ["Y15-74"]  # taux de chômage standard (population active 15-74 ans)

# Allemagne + 16 Länder (NUTS 1) + régions NUTS 2 allemandes.
GERMANY_GEO_CODES = [
    "DE",
    # NUTS 1
    "DE1", "DE2", "DE3", "DE4", "DE5", "DE6", "DE7", "DE8",
    "DE9", "DEA", "DEB", "DEC", "DED", "DEE", "DEF", "DEG",
    # NUTS 2
    "DE11", "DE12", "DE13", "DE14",
    "DE21", "DE22", "DE23", "DE24", "DE25", "DE26", "DE27",
    "DE30", "DE40", "DE50", "DE60",
    "DE71", "DE72", "DE73", "DE80",
    "DE91", "DE92", "DE93", "DE94",
    "DEA1", "DEA2", "DEA3", "DEA4", "DEA5",
    "DEB1", "DEB2", "DEB3", "DEC0",
    "DED2", "DED4", "DED5", "DEE0", "DEF0", "DEG0",
]


def download_dataset(dataset_code: str = DATASET_CODE) -> Path:
    """Télécharge et archive les géographies allemandes ciblées."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{API_BASE_URL}/{dataset_code}"
    params = {
        "lang": LANGUAGE,
        "geo": GERMANY_GEO_CODES,  # requests répète geo=... pour chaque valeur de la liste
        "sex": SEX_CODES,
        "age": AGE_CODES,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_file = OUTPUT_DIR / f"{dataset_code}_DE_regions_{timestamp}.json"
    metadata_file = OUTPUT_DIR / f"{dataset_code}_DE_regions_{timestamp}_metadata.json"

    logging.info("Téléchargement Eurostat : %s (%s géographies)", dataset_code, len(GERMANY_GEO_CODES))
    response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("La réponse Eurostat n'est pas un objet JSON attendu.")

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)

    metadata = {
        "source": "Eurostat",
        "dataset_code": dataset_code,
        "geographical_filter": GERMANY_GEO_CODES,
        "sex_filter": SEX_CODES,
        "age_filter": AGE_CODES,
        "request_url": response.url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "raw_file": output_file.name,
    }
    with metadata_file.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    logging.info("Fichier brut enregistré : %s", output_file)
    return output_file


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        result = download_dataset()
        print(f"Extraction terminée : {result}")
    except requests.RequestException as exc:
        logging.error("Erreur HTTP/réseau lors de l'extraction : %s", exc)
        raise


if __name__ == "__main__":
    main()