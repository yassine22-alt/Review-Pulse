"""Measure the relation arm (xeval/relation_arm.py) against a labelled set of requirements about how spaces connect.

    python scripts/relations_eval.py [--model qwen2.5:7b]

The set is small and written by hand: English, French, German and Spanish sentences of the four relation kinds (a forbidden
link, a required link, a route to an exit with or without spaces to avoid, a door or opening for every space), and sentences that
are not relations at all. For each, the correct choices are written down; the correct rule is the one the arm's own templates
build from them, so what is measured is the model's choosing. A drafted rule is right when its text is the correct rule's text. Reported: right, declined (left to the free-form arm), and wrong
but accepted, the number that matters most. For the non-relations the only good outcome is a decline.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "tests/fixtures")

import handmade  # noqa: E402

from reviewpulse.factgraph.convert import to_catalogue  # noqa: E402
from reviewpulse.factgraph.from_building import from_building  # noqa: E402
from reviewpulse.interpreter.context import assemble_context  # noqa: E402
from reviewpulse.rules.clauses import split_text  # noqa: E402
from reviewpulse.xeval.drafters import BoundedOllama  # noqa: E402
from reviewpulse.xeval.expr_ir import to_text  # noqa: E402
from reviewpulse.xeval.relation_arm import draft_relation  # noqa: E402

# (sentence, relation, first, second, subject, avoid); relation None marks a sentence that is not a relation
SET = [
    ("No door or opening connects a garage directly to a bedroom.", "no_link", "garage", "bedroom", (), ()),
    ("Aucune porte ne doit relier directement un garage à une chambre.", "no_link", "garage", "bedroom", (), ()),
    ("Ein Badezimmer darf nicht direkt mit der Küche verbunden sein.", "no_link", "bathroom", "kitchen", (), ()),
    ("La cocina no debe comunicar directamente con el dormitorio.", "no_link", "kitchen", "bedroom", (), ()),
    ("A storage room shall not open directly onto a bedroom.", "no_link", "storage", "bedroom", (), ()),
    ("Every bedroom shall be directly connected to a corridor.", "must_link", "bedroom", "corridor", (), ()),
    ("Jede Küche muss direkt mit dem Wohnzimmer verbunden sein.", "must_link", "kitchen", "living", (), ()),
    ("Le séjour doit communiquer directement avec la cuisine.", "must_link", "living", "kitchen", (), ()),
    ("Every bedroom shall have a route to an exit.", "route", None, None, ("bedroom",), ()),
    ("Every bedroom or kitchen reaches an exit without passing through a bathroom or a WC.", "route", None, None,
     ("bedroom", "kitchen"), ("bathroom", "wc")),
    ("Chaque chambre doit avoir un accès à la sortie sans traverser la salle de bains.", "route", None, None,
     ("bedroom",), ("bathroom",)),
    ("Jedes Schlafzimmer muss einen Weg zum Ausgang haben.", "route", None, None, ("bedroom",), ()),
    ("From any room there must be a route to the exit.", "route", None, None, (), ()),
    ("Every enclosed room has at least one door or opening.", "has_passage", None, None, (), ()),
    ("Every bathroom shall have at least one door.", "has_passage", None, None, ("bathroom",), ()),
    ("Chaque chambre doit posséder au moins une porte.", "has_passage", None, None, ("bedroom",), ()),
    ("Walls shall be finished in a light colour.", None, None, None, (), ()),
    ("Bedrooms shall have natural light.", None, None, None, (), ()),
    ("The kitchen shall be at least 6 m2.", None, None, None, (), ()),
    ("Doors shall open outwards.", None, None, None, (), ()),
    ("Les portes coupe-feu doivent être à fermeture automatique.", None, None, None, (), ()),
    ("Die Fenster müssen dreifach verglast sein.", None, None, None, (), ()),
]


class Oracle:
    """The correct choices for one sentence, answered by the role of each question."""

    def __init__(self, relation, first, second, subject, avoid):
        self.relation, self.first, self.second, self.subject, self.avoid = relation, first, second, list(subject), list(avoid)

    def complete(self, system, user, schema):
        key = next(iter(schema["properties"]))
        if key == "choice":
            if "Which kind of requirement" in system:
                return {"choice": self.relation}
            if "SECOND kind" in system:
                return {"choice": self.second}
            if "FIRST kind" in system:
                return {"choice": self.first}
            if "every room or space" in system:           # the subject is every space exactly when the correct choices name none
                return {"choice": "spaces"}
            if "THEMSELVES have the route" in system:
                c = re.search(r"category '([^']*)'", system).group(1).replace(" ", "_")
                return {"choice": "yes" if c in self.subject else "no"}
            return {"choice": "EXIT"}
        if "NOT pass through" in system:
            return {"values": self.avoid}
        if getattr(self, "confuse", False):          # a small model lists the spaces to avoid among the subjects as well
            return {"values": sorted(set(self.subject) | set(self.avoid))}
        return {"values": self.subject}


def same_rule(a, b) -> bool:
    """Both rules come from the same templates, so equal choices give the same rule text (the kind lists are sorted)."""
    return to_text(a.model_dump(mode="json")["requirement"]) == to_text(b.model_dump(mode="json")["requirement"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b")
    args = ap.parse_args()
    cat = to_catalogue(from_building(handmade.build(), complete=True))
    client = BoundedOllama(model=args.model, num_predict=120)
    tally = {"right": 0, "declined": 0, "wrong": 0}
    neg = {"declined": 0, "wrong": 0}
    n_pos = sum(1 for s in SET if s[1])
    for sentence, relation, first, second, subject, avoid in SET:
        text = f"Art. 1 {sentence}\n"
        item = SimpleNamespace(id="x", text=sentence, catalogue=cat, lang=None,
                               ctx=assemble_context("d", text, split_text(text), "Art. 1"))
        t0 = time.time()
        got = draft_relation("expr_relation", item, client)
        if relation is None:
            neg["wrong" if got.program is not None else "declined"] += 1
            print(f"  not a relation  {'ACCEPTED' if got.program is not None else 'declined':9} {time.time() - t0:4.0f}s  {sentence[:70]}", flush=True)
            continue
        gold = draft_relation("expr_relation", item, Oracle(relation, first, second, subject, avoid))
        if got.program is None:
            tally["declined"] += 1
            verdict = f"declined ({got.detail[:40]})"
        elif gold.program is not None and same_rule(gold.program, got.program):
            tally["right"] += 1
            verdict = "right"
        else:
            tally["wrong"] += 1
            verdict = "WRONG"
        print(f"  {relation:11} {verdict:48} {time.time() - t0:4.0f}s  {sentence[:60]}", flush=True)
    print(f"\n{args.model}: {n_pos} relation sentences: right {tally['right']}, declined {tally['declined']}, "
          f"wrong but accepted {tally['wrong']}")
    print(f"{len(SET) - n_pos} sentences that are not relations: declined {neg['declined']}, wrongly accepted {neg['wrong']}")
    _ = Path


if __name__ == "__main__":
    main()
