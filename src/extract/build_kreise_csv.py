"""
Génère kreise_ba.csv à partir de la liste officielle des régions de la BA.

Source (citée dans la doc API de la BA) :
https://statistik.arbeitsagentur.de/Auswahl/Layout/Statistiktabellen/JS/DR-LZR-persistListenfelderJSON.js

ATTENTION : la structure exacte de ce fichier JS n'a pas pu être vérifiée
à l'écriture de ce script. Le script sauvegarde donc d'abord le fichier brut
(data/raw/ba_regions/regions.js) et affiche les clés trouvées, pour que tu
puisses ajuster KREIS_KEY_HINT si besoin.
"""

import csv
import json
import re
from pathlib import Path

import requests

URL = (
    "https://statistik.arbeitsagentur.de/Auswahl/Layout/Statistiktabellen/JS/"
    "DR-LZR-persistListenfelderJSON.js"
)
RAW_PATH = Path("data/raw/ba_regions/regions.js")
OUTPUT_CSV = Path("config/kreise_ba.csv")
KREIS_KEY_HINT = "kreis"  # sous-chaîne (insensible à la casse) de la clé cherchée
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ThesisDataWarehouse/1.0)"}


def download() -> str:
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(response.content)  # brut, non modifié
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        return response.content.decode("latin-1")


def extract_json(js_text: str):
    """Isole l'objet/tableau JSON dans le fichier JS (ex: var x = {...};)."""
    match = re.search(r"[\{\[]", js_text)
    if not match:
        raise ValueError("Aucun JSON trouvé dans le fichier.")
    start = match.start()
    end = max(js_text.rfind("}"), js_text.rfind("]")) + 1
    return json.loads(js_text[start:end])


def collect_strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [s for item in node for s in collect_strings(item)]
    if isinstance(node, dict):
        return [s for value in node.values() for s in collect_strings(value)]
    return []


def find_kreise(node, path="") -> list[str]:
    """Cherche récursivement les clés dont le nom contient KREIS_KEY_HINT."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if KREIS_KEY_HINT in key.lower():
                print(f"Clé trouvée : {path}/{key}")
                found += collect_strings(value)
            else:
                found += find_kreise(value, f"{path}/{key}")
    elif isinstance(node, list):
        for item in node:
            found += find_kreise(item, path)
    return found


def main():
    data = extract_json(download())
    if isinstance(data, dict):
        print("Clés de premier niveau :", list(data.keys()))

    kreise = sorted(set(find_kreise(data)))
    if not kreise:
        raise SystemExit("Aucun Kreis trouvé : ouvre regions.js et ajuste KREIS_KEY_HINT.")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["kreis"])
        writer.writerows([[name] for name in kreise])
    print(f"{len(kreise)} Kreise écrits dans {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
