# Data Directory

This directory contains reference information and selected data quality reports.

## Directory policy

- `raw/`: source extracts are excluded from Git.
- `processed/`: large processed datasets are excluded.
- `processed/*qc_report.json`: selected quality reports are tracked.
- `reference/`: selected geographical reference files are tracked.

## Rebuilding the datasets

Raw datasets must be obtained from the original providers:

- Bundesagentur für Arbeit
- Eurostat
- Official geographical reference sources

The extraction and transformation scripts are located in `src/extract/` and `src/transform/`.

Please check the source licensing terms before redistributing any dataset.
