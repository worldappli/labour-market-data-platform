from __future__ import annotations

from airflow.models.baseoperator import cross_downstream
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.providers.standard.operators.python import PythonOperator

import psycopg2
from contextlib import contextmanager



# ============================================================
# CONFIGURATION DU PROJET
# ============================================================

PROJECT_ROOT = Path("/opt/airflow/labour-market-dwh")

PYTHON = sys.executable

RAW_BA_DIR = PROJECT_ROOT / "data" / "raw" / "ba_arbeitslosigkeit"
RAW_EUROSTAT_DIR = PROJECT_ROOT / "data" / "raw" / "eurostat"

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

BA_REFERENCE = PROJECT_ROOT / "data" / "reference" / "kreise_ba.csv"

BA_OUTPUT = PROCESSED_DIR / "ba_arbeitslosigkeit.csv"
EUROSTAT_OUTPUT = PROCESSED_DIR / "eurostat_allemagne.csv"

BA_QC_REPORT = PROCESSED_DIR / "ba_qc_report.json"
EUROSTAT_QC_REPORT = PROCESSED_DIR / "eurostat_qc_report.json"

def get_latest_eurostat_file() -> Path:
    candidates = [
        path
        for path in RAW_EUROSTAT_DIR.glob("lfst_r_lfu3rt_DE_regions_*.json")
        if not path.name.endswith("_metadata.json")
    ]

    if not candidates:
        raise FileNotFoundError(
            f"Aucun fichier de données Eurostat trouvé dans {RAW_EUROSTAT_DIR}"
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)

# ============================================================
# OUTILS COMMUNS
# ============================================================

def run_script(script_path: Path, *args: str) -> None:
    """
    Exécute un script Python existant depuis la racine du projet.
    Toute erreur du script fait échouer la tâche Airflow.
    """
    if not script_path.is_file():
        raise AirflowException(
            f"Script introuvable : {script_path}"
        )

    command = [
        PYTHON,
        str(script_path),
        *args,
    ]

    logging.info("Exécution : %s", " ".join(command))

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout:
        logging.info("Sortie du script :\n%s", result.stdout)

    if result.stderr:
        logging.info("Messages du script :\n%s", result.stderr)

    if result.returncode != 0:
        raise AirflowException(
            f"Échec du script {script_path.name} "
            f"(code retour {result.returncode})."
        )


def require_file(path: Path) -> None:
    """Vérifie l'existence et la non-vacuité d'un fichier."""
    if not path.is_file():
        raise AirflowException(f"Fichier absent : {path}")

    if path.stat().st_size == 0:
        raise AirflowException(f"Fichier vide : {path}")

    logging.info(
        "Fichier vérifié : %s (%s octets)",
        path,
        path.stat().st_size,
    )

# ============================================================
# CONNEXION POSTGRESQL ET EXÉCUTION DES SCRIPTS SQL
# ============================================================

@contextmanager
def postgres_connection():
    """
    Ouvre une connexion au Data Warehouse.
    Les identifiants doivent être fournis par l'environnement Airflow.
    """
    required_vars = [
        "DW_HOST",
        "DW_PORT",
        "DW_DATABASE",
        "DW_USER",
        "DW_PASSWORD",
    ]

    missing = [name for name in required_vars if not os.getenv(name)]

    if missing:
        raise AirflowException(
            f"Variables PostgreSQL manquantes : {', '.join(missing)}"
        )

    connection = psycopg2.connect(
        host=os.environ["DW_HOST"],
        port=os.environ["DW_PORT"],
        dbname=os.environ["DW_DATABASE"],
        user=os.environ["DW_USER"],
        password=os.environ["DW_PASSWORD"],
        connect_timeout=15,
    )

    try:
        yield connection
    finally:
        connection.close()


def execute_sql_file(sql_file: Path) -> None:
    """
    Exécute un script SQL dans une transaction.
    Une erreur annule la transaction et fait échouer la tâche Airflow.
    """
    if not sql_file.is_file():
        raise AirflowException(f"Script SQL introuvable : {sql_file}")

    sql = sql_file.read_text(encoding="utf-8")

    if not sql.strip():
        raise AirflowException(f"Script SQL vide : {sql_file}")

    logging.info("Exécution du script SQL : %s", sql_file.name)

    with postgres_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)

            connection.commit()
            logging.info("Script SQL exécuté avec succès : %s", sql_file.name)

        except Exception:
            connection.rollback()
            logging.exception("Échec du script SQL : %s", sql_file.name)
            raise


# ============================================================
# CHARGEMENT STAGING
# ============================================================

def load_staging_ba() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "staging" / "ba.sql"
    )


def load_staging_eurostat() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "staging" / "eurostat.sql"
    )


# ============================================================
# CHARGEMENT RAW VAULT
# ============================================================

def load_raw_vault() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "data_vault" / "chargement.sql"
    )


# ============================================================
# CHARGEMENT DES SATELLITES
# ============================================================

def load_satellites() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "data_vault" / "chargement_sat.sql"
    )


# ============================================================
# CHARGEMENT DES DIMENSIONS ET DES FAITS
# ============================================================

def load_data_mart_dimensions() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "data_mart" / "chargement_data_mart.sql"
    )


def load_data_mart_facts() -> None:
    execute_sql_file(
        PROJECT_ROOT / "src" / "postgres" / "data_mart" / "data_mart_fact.sql"
    )
# ============================================================
# EXTRACTION BA
# ============================================================

def extract_ba() -> None:
    """
    Exécute l'extraction BA existante.

    Le script écrit ses fichiers RAW dans le dossier configuré
    dans ba_api_ingest.py.
    """
    require_file(BA_REFERENCE)

    RAW_BA_DIR.mkdir(parents=True, exist_ok=True)

    script = PROJECT_ROOT / "src" / "extract" / "ba_api_ingest.py"

    run_script(script)

    # Vérification de la présence des données extraites.
    csv_files = list(RAW_BA_DIR.glob("*.csv"))

    if not csv_files:
        raise AirflowException(
            f"Aucun CSV BA trouvé dans {RAW_BA_DIR}. "
            "Vérifie le chemin de sortie de ba_api_ingest.py."
        )

    logging.info(
        "Extraction BA terminée : %d fichiers CSV détectés.",
        len(csv_files),
    )


# ============================================================
# EXTRACTION EUROSTAT
# ============================================================

def extract_eurostat() -> None:
    """Exécute l'extraction Eurostat existante."""
    RAW_EUROSTAT_DIR.mkdir(parents=True, exist_ok=True)

    script = PROJECT_ROOT / "src" / "extract" / "eurostat_ingest.py"

    run_script(script)

    json_files = list(RAW_EUROSTAT_DIR.glob("*.json"))

    if not json_files:
        raise AirflowException(
            f"Aucun JSON Eurostat trouvé dans {RAW_EUROSTAT_DIR}."
        )

    latest_file = max(
        json_files,
        key=lambda file: file.stat().st_mtime,
    )

    require_file(latest_file)

    logging.info(
        "Dernier JSON Eurostat détecté : %s",
        latest_file,
    )


# ============================================================
# TRANSFORMATION BA
# ============================================================

def transform_ba() -> None:
    """Consolide et normalise les fichiers BA."""
    require_file(BA_REFERENCE)

    RAW_BA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    script = PROJECT_ROOT / "src" / "transform" / "ba_transform.py"

    run_script(
        script,
        "--input", str(RAW_BA_DIR),
        "--reference", str(BA_REFERENCE),
        "--output", str(BA_OUTPUT),
    )

    require_file(BA_OUTPUT)


# ============================================================
# TRANSFORMATION EUROSTAT
# ============================================================
def transform_eurostat() -> None:
    """Transforme le dernier JSON de données Eurostat en CSV."""

    input_file = get_latest_eurostat_file()

    require_file(input_file)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    script = (
        PROJECT_ROOT
        / "src"
        / "transform"
        / "eurostat_transform.py"
    )

    run_script(
        script,
        "--input", str(input_file),
        "--output", str(EUROSTAT_OUTPUT),
    )

    require_file(EUROSTAT_OUTPUT)
# ============================================================
# CONTRÔLE QUALITÉ BA
# ============================================================

def quality_check_ba() -> None:
    """Contrôle la qualité du CSV BA consolidé."""
    require_file(BA_OUTPUT)

    script = (
        PROJECT_ROOT
        / "src"
        / "validation"
        / "ba_quality_check.py"
    )

    run_script(
        script,
        "--input", str(BA_OUTPUT),
        "--report", str(BA_QC_REPORT),
    )

    require_file(BA_QC_REPORT)

    logging.info("Contrôle qualité BA réussi.")


# ============================================================
# CONTRÔLE QUALITÉ EUROSTAT
# ============================================================

def quality_check_eurostat() -> None:
    """Contrôle la qualité du CSV Eurostat."""
    require_file(EUROSTAT_OUTPUT)

    script = (
        PROJECT_ROOT
        / "src"
        / "validation"
        / "eurostat_quality_check.py"
    )

    run_script(
        script,
        "--input", str(EUROSTAT_OUTPUT),
        "--report", str(EUROSTAT_QC_REPORT),
    )

    require_file(EUROSTAT_QC_REPORT)

    logging.info("Contrôle qualité Eurostat réussi.")


# ============================================================
# DÉFINITION DU DAG
# ============================================================

with DAG(
    dag_id="labour_market_pipeline",
    description=(
        "Pipeline ETL du mémoire : "
        "BA et Eurostat, transformations et contrôles qualité."
    ),
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "data_engineering",
        "retries": 1,
    },
    tags=[
        "memoire",
        "data-engineering",
        "ETL",
        "BA",
        "Eurostat",
    ],
) as dag:

    task_extract_ba = PythonOperator(
        task_id="extract_ba",
        python_callable=extract_ba,
    )

    task_extract_eurostat = PythonOperator(
        task_id="extract_eurostat",
        python_callable=extract_eurostat,
    )

    task_transform_ba = PythonOperator(
        task_id="transform_ba",
        python_callable=transform_ba,
    )

    task_transform_eurostat = PythonOperator(
        task_id="transform_eurostat",
        python_callable=transform_eurostat,
    )

    task_quality_ba = PythonOperator(
        task_id="quality_check_ba",
        python_callable=quality_check_ba,
    )

    task_quality_eurostat = PythonOperator(
        task_id="quality_check_eurostat",
        python_callable=quality_check_eurostat,
    )
    task_load_staging_ba = PythonOperator(
        task_id="load_staging_ba",
        python_callable=load_staging_ba,
    )

    task_load_staging_eurostat = PythonOperator(
        task_id="load_staging_eurostat",
        python_callable=load_staging_eurostat,
    )

    task_load_raw_vault = PythonOperator(
        task_id="load_raw_vault",
        python_callable=load_raw_vault,
    )

    task_load_satellites = PythonOperator(
        task_id="load_satellites",
        python_callable=load_satellites,
    )

    task_load_data_mart_dimensions = PythonOperator(
        task_id="load_data_mart_dimensions",
        python_callable=load_data_mart_dimensions,
    )

    task_load_data_mart_facts = PythonOperator(
        task_id="load_data_mart_facts",
        python_callable=load_data_mart_facts,
    )

    # Les extractions sont indépendantes.
    # Branche BA
    task_extract_ba >> task_transform_ba >> task_quality_ba

    # Branche Eurostat
    task_extract_eurostat >> task_transform_eurostat >> task_quality_eurostat

    # Chargement du staging après les deux contrôles qualité

    # Contrôles qualité terminés avant le chargement du staging
    cross_downstream(
        [task_quality_ba, task_quality_eurostat],
        [task_load_staging_ba, task_load_staging_eurostat],
    )

    # Staging -> Raw Vault
    [task_load_staging_ba, task_load_staging_eurostat] >> task_load_raw_vault

    # Raw Vault -> Satellites
    task_load_raw_vault >> task_load_satellites

    # Satellites -> Dimensions du Data Mart
    task_load_satellites >> task_load_data_mart_dimensions

    # Dimensions -> Faits
    task_load_data_mart_dimensions >> task_load_data_mart_facts