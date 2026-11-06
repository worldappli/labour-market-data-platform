#!/usr/bin/env python3
"""
T9 - Verhalten bei fehlerhaften Eingaben (BA-Transformation und Qualitaetspruefung).

Aufruf im Projektstamm (dort, wo dags/, src/ und data/ liegen):
    python tests/t9_fehlerhafte_eingaben.py

Es werden KEINE Projektdaten veraendert: Alle Testfaelle laufen in einem
temporaeren Ordner, die Ausgabedateien ebenfalls.
Ergebnis: Tabelle auf dem Bildschirm und tests/t9_ergebnis.txt.
"""
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ba_arbeitslosigkeit"
REF = ROOT / "data" / "reference" / "kreise_ba.csv"
PROCESSED = ROOT / "data" / "processed" / "ba_arbeitslosigkeit.csv"
TRANSFORM = ROOT / "src" / "transform" / "ba_transform.py"
QC = ROOT / "src" / "validation" / "ba_quality_check.py"

KEYWORDS = ("Valeur", "conflit", "Kreis", "vide", "introuvable", "erreur",
            "Erreur", "Error", "inattendue", "absent")


def read_lines(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def write_lines(path, lines):
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=";").writerows(lines)


def header_index(lines):
    for i, row in enumerate(lines):
        cells = [c.strip() for c in row]
        if "Berichtsmonat" in cells and "Arbeitslose" in cells:
            return i
    raise RuntimeError("Kein Header in der Quelldatei gefunden")


def first_numeric_cell(lines):
    h = header_index(lines)
    col = [c.strip() for c in lines[h]].index("Arbeitslose")
    for i in range(h + 1, len(lines)):
        row = lines[i]
        if len(row) > col and row[col].replace(" ", "").isdigit():
            return i, col
    raise RuntimeError("Keine numerische Beobachtung gefunden")


def build_case(base, name, src, mutate=None, extra_copy=None):
    d = base / name
    d.mkdir(parents=True)
    lines = read_lines(src)
    if mutate:
        lines = mutate(lines)
    write_lines(d / "a_test.csv", lines)
    if extra_copy:
        write_lines(d / "b_test.csv", extra_copy(read_lines(src)))
    return d


def m_set(value):
    def f(lines):
        i, c = first_numeric_cell(lines)
        lines[i][c] = value
        return lines
    return f


def m_plus_one(lines):
    i, c = first_numeric_cell(lines)
    lines[i][c] = str(int(lines[i][c].replace(" ", "")) + 1)
    return lines


def m_unknown_kreis(lines):
    for row in lines:
        if row and row[0].strip().lower() == "kreis:" and len(row) > 1:
            row[1] = "Testhausen"
            return lines
    raise RuntimeError("Zeile 'Kreis:' nicht gefunden")


def m_no_header(lines):
    h = header_index(lines)
    del lines[h]
    return lines


def run_transform(case_dir, out):
    r = subprocess.run(
        [sys.executable, str(TRANSFORM), "--input", str(case_dir),
         "--reference", str(REF), "--output", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    hits = [l.strip() for l in text.splitlines()
            if any(k in l for k in KEYWORDS)]
    msg = hits[-1] if hits else " | ".join(
        [l.strip() for l in text.splitlines() if l.strip()][-2:])
    return r.returncode, msg[:200]


def main():
    for p in (RAW, REF, PROCESSED, TRANSFORM, QC):
        if not p.exists():
            sys.exit(f"Pfad fehlt: {p}  (Aufruf aus dem Projektstamm?)")
    src = sorted(RAW.glob("*.csv"))[0]
    print(f"Quelldatei fuer die Testfaelle: {src.name}\n")

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        out = base / "out.csv"

        cases = [
            ("N1", "negativer Wert in Rohdatei (-5)", "Abbruch",
             build_case(base, "n1", src, m_set("-5"))),
            ("N2", "Text statt Zahl ('abc')", "Abbruch",
             build_case(base, "n2", src, m_set("abc"))),
            ("N3", "widerspruechliche Doppelwerte (zwei Dateien, Wert +1)",
             "Abbruch", build_case(base, "n3", src, None, m_plus_one)),
            ("N4", "identische Doppeldatei (Kontrolle)", "kein Abbruch",
             build_case(base, "n4", src, None, lambda l: l)),
            ("N5", "unbekannter Kreis ('Testhausen')", "Abbruch",
             build_case(base, "n5", src, m_unknown_kreis)),
            ("N6", "leere Datei", "Abbruch", None),
            ("N7", "Header-Zeile entfernt", "Abbruch",
             build_case(base, "n7", src, m_no_header)),
        ]
        # leere Datei
        d6 = base / "n6"
        d6.mkdir()
        (d6 / "leer.csv").write_text("", encoding="utf-8")
        cases[5] = (cases[5][0], cases[5][1], cases[5][2], d6)

        for cid, desc, expected, d in cases:
            if out.exists():
                out.unlink()
            rc, msg = run_transform(d, out)
            failed = rc != 0
            ok = failed if expected == "Abbruch" else not failed
            results.append((cid, desc, expected, f"Exit-Code {rc}", msg,
                            "BESTANDEN" if ok else "ABWEICHUNG"))

        # N8: negativer Wert NACH der Transformation -> QC meldet, blockiert nicht
        tmp_csv = base / "processed_neg.csv"
        with PROCESSED.open(encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f, delimiter=";")
            fields = rd.fieldnames
            rows = list(rd)
        rows[0]["arbeitslose"] = "-5"
        with tmp_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        rep = base / "qc.json"
        r = subprocess.run(
            [sys.executable, str(QC), "--input", str(tmp_csv),
             "--report", str(rep)],
            cwd=ROOT, capture_output=True, text=True)
        neg = "Bericht nicht erzeugt"
        flagged = False
        if rep.exists():
            data = json.loads(rep.read_text(encoding="utf-8"))
            n = data.get("negative_value_count", 0)
            flagged = n > 0
            neg = f"negative_value_count = {n}"

        if r.returncode != 0:
            print("\n=== DEBUG N8 : STDOUT ===")
            print(r.stdout)
            print("\n=== DEBUG N8 : STDERR ===")
            print(r.stderr)

        ok = r.returncode == 0 and flagged
        results.append(("N8", "negativer Wert im aufbereiteten CSV (QC-Skript)",
                        "meldet, blockiert nicht", f"Exit-Code {r.returncode}",
                        neg, "BESTANDEN" if ok else "ABWEICHUNG"))

    lines = ["Nr | Testfall | Erwartung | Ergebnis | Meldung | Bewertung"]
    for row in results:
        lines.append(" | ".join(row))
    text = "\n".join(lines)
    print(text)
    (ROOT / "tests").mkdir(exist_ok=True)
    (ROOT / "tests" / "t9_ergebnis.txt").write_text(text, encoding="utf-8")
    print("\nGespeichert: tests/t9_ergebnis.txt")


if __name__ == "__main__":
    main()
