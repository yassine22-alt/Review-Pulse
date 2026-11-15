"""Measure the answerability triage (src/reviewpulse/interpreter/triage.py).

    python scripts/triage_eval.py [--n 80] [--model qwen2.5:7b]

Two numbers, because the two errors cost differently:
  recall       of clauses that ARE checkable on a plan (synthetic corpus, several languages, known by construction), the share
               the triage keeps. A miss hides a requirement until a reviewer reads it anyway, so this is the number to push to 1.
  specificity  of sentences no plan can answer (written below: process, money, materials, signage, dates, in several
               languages), the share the triage drops. A miss only costs reading time.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reviewpulse.interpreter.triage import triage
from reviewpulse.xeval.drafters import BoundedOllama

NOT_ON_A_PLAN = [
    ("en", "The application shall be submitted to the building authority at least 30 days before work starts."),
    ("en", "The contractor shall hold a valid licence and shall keep records of all inspections for five years."),
    ("en", "Insulation materials shall have a thermal conductivity not greater than 0.04 W/mK."),
    ("en", "Concrete used in foundations shall have a compressive strength of at least 25 MPa."),
    ("en", "Warning signs shall be written in letters at least 50 mm high."),
    ("en", "The fee for a revised submission is 120 euros and is payable on filing."),
    ("en", "This standard applies to buildings for which a permit is requested after 1 January 2020."),
    ("en", "Fire alarm systems shall be tested every six months by a qualified person."),
    ("fr", "Le dossier doit être déposé en mairie au moins un mois avant le début des travaux."),
    ("fr", "Les matériaux d'isolation doivent présenter une résistance thermique supérieure à 5 m2.K/W."),
    ("fr", "Le maître d'ouvrage doit souscrire une assurance dommages-ouvrage avant l'ouverture du chantier."),
    ("fr", "Les panneaux de signalisation doivent utiliser des caractères d'au moins 50 mm de hauteur."),
    ("de", "Der Bauherr muss den Antrag mindestens 30 Tage vor Baubeginn bei der Behörde einreichen."),
    ("de", "Die Dämmstoffe müssen eine Wärmeleitfähigkeit von höchstens 0,04 W/mK aufweisen."),
    ("de", "Brandmeldeanlagen sind alle sechs Monate von einer Fachkraft zu prüfen."),
    ("es", "La solicitud debe presentarse ante la autoridad al menos 30 días antes del inicio de las obras."),
    ("es", "El hormigón de las cimentaciones tendrá una resistencia mínima de 25 MPa."),
    ("es", "Las instalaciones de protección contra incendios se revisarán cada seis meses."),
    ("it", "La domanda deve essere presentata all'autorità almeno 30 giorni prima dell'inizio dei lavori."),
    ("nl", "De aanvraag moet minstens 30 dagen voor de start van de werken worden ingediend."),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--corpus", default="reports/extractor_eval/corpus.jsonl")
    args = ap.parse_args()
    items = [json.loads(line) for line in Path(args.corpus).read_text(encoding="utf-8").splitlines() if line.strip()]
    random.Random(7).shuffle(items)
    items = items[: args.n]
    client = BoundedOllama(model=args.model, num_predict=200)
    by_lang: dict[str, list[bool]] = {}
    missed = []
    for it in items:
        ok, why = triage(client, it["text"], it["catalogue"])
        by_lang.setdefault(it["lang"], []).append(ok)
        if not ok:
            missed.append((it["lang"], it["text"][:110], why))
    kept = sum(sum(v) for v in by_lang.values())
    print(f"recall {kept}/{len(items)} = {kept / len(items):.2f}  by language: "
          + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by_lang.items())))
    for m in missed:
        print("  MISSED", m)
    catalogue = items[0]["catalogue"]
    dropped = 0
    for lang, text in NOT_ON_A_PLAN:
        ok, why = triage(client, text, catalogue)
        dropped += not ok
        if ok:
            print(f"  KEPT (should drop) [{lang}] {text[:90]}")
    print(f"specificity {dropped}/{len(NOT_ON_A_PLAN)} = {dropped / len(NOT_ON_A_PLAN):.2f}")


if __name__ == "__main__":
    main()
