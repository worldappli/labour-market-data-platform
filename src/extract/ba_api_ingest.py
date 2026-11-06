"""
Ingestion des données "Eckwerte Arbeitslosigkeit" (chômage) de la Statistik
der Bundesagentur für Arbeit (BA), par Kreis / kreisfreie Stadt.

Documentation officielle de l'API :
https://statistik.arbeitsagentur.de/DE/Statischer-Content/Service/API/API-ALO-Zeitreihe.html

Principe :
- Un appel = une région (limite technique côté BA), il faut donc boucler.
- Réponse CSV brute -> à stocker telle quelle dans le schéma raw/staging,
  la validation/normalisation vient dans une étape séparée (voir consigne
  du mémoire : "Aufbereitung" doit rester distincte de l'ingestion).
"""

import csv
import time
from pathlib import Path
import pandas as pd

import requests

BASE_URL = (
    "https://statistik-dr.arbeitsagentur.de/bifrontend/bids-api/ct/v1/"
    "tableFetch/csv/EckwerteZeitreiheALO"
)
OUTPUT_DIR = Path("data/raw/ba_arbeitslosigkeit")
HEADERS = {
    # Certains endpoints publics bloquent les clients sans User-Agent explicite.
    "User-Agent": "Mozilla/5.0 (compatible; ThesisDataWarehouse/1.0)"
}
REQUEST_DELAY_SECONDS = 1.0  # courtoisie vis-à-vis de l'API, pas de limite documentée

# Noms officiels des Kreise/kreisfreie Städte à récupérer.
# Les noms DOIVENT correspondre exactement à la nomenclature officielle,
# sinon l'API renvoie {"err": "501 Datensatz leer."}.
# Liste de référence :
# https://statistik.arbeitsagentur.de/Auswahl/Layout/Statistiktabellen/JS/DR-LZR-persistListenfelderJSON.js
'''KREISE = [
    "Region Hannover",
    "Landkreis Emsland",
    # ... compléter avec les Kreise de ta zone d'étude
]'''

KREISE_FILE = Path("data/reference/kreise_ba.csv")

def load_kreise():
    """Charge les Kreise depuis le fichier de référence BA."""

    df = pd.read_csv(KREISE_FILE, dtype=str, sep=";")
    df.columns = df.columns.str.strip().str.lower()

    # Le fichier de référence utilise la colonne 'name'.
    # Le script utilise ensuite 'kreis_name'.
    if "name" in df.columns and "kreis_name" not in df.columns:
        df = df.rename(columns={"name": "kreis_name"})

    required_columns = {"kreis_name", "ba_id", "ags"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Colonnes manquantes dans {KREISE_FILE}: "
            f"{sorted(missing_columns)}. "
            f"Colonnes disponibles: {df.columns.tolist()}"
        )

    df["kreis_name"] = df["kreis_name"].str.strip()
    df["ba_id"] = df["ba_id"].str.strip()
    df["ags"] = df["ags"].str.strip()

    return df


KREISE = load_kreise()

def fetch_kreis(kreis_name: str) -> str:
    """Récupère le CSV brut pour un Kreis donné (texte, pas encore parsé)."""
    params = {"Kreis": kreis_name}
    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()

    # L'API renvoie parfois un 200 avec un message d'erreur JSON dans le corps
    # (nom de région non reconnu) au lieu d'un vrai CSV : on le détecte ici.
    if response.text.strip().startswith('{"err"'):
        raise ValueError(f"Réponse d'erreur de l'API pour '{kreis_name}': {response.text}")

    return response.text


def save_raw(kreis_name: str, content: str) -> Path:
    """Sauvegarde le CSV brut, sans transformation, avec un nom de fichier sûr."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = kreis_name.replace(" ", "_").replace("/", "-")
    filepath = OUTPUT_DIR / f"{safe_name}.csv"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def main():
    results = {"ok": [], "erreurs": []}

    for kreis in KREISE:
        try:
            content = fetch_kreis(kreis)
            path = save_raw(kreis, content)
            print(f"[OK] {kreis} -> {path}")
            results["ok"].append(kreis)
        except (requests.HTTPError, ValueError) as e:
            print(f"[ERREUR] {kreis}: {e}")
            results["erreurs"].append(kreis)
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nTerminé : {len(results['ok'])} OK, {len(results['erreurs'])} erreurs.")
    if results["erreurs"]:
        print("Kreise en erreur (vérifier l'orthographe officielle) :", results["erreurs"])

if __name__ == "__main__":
    main()
