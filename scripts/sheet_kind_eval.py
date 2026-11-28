"""Measure sheet recognition on real drawing pages whose kind an AI grader judged from renders (not the system under test).

    python scripts/sheet_kind_eval.py            (needs reports/real_plans/*.png from scripts/real_plan_study.py)

Judgements are in LABELS below: the set of acceptable kinds per page, and whether the page shows a floor plan that a
reviewer would want checked. Pages where several kinds are fair (a framing elevation is a structural drawing and an
elevation) list all of them. Hand sketches are marked "don't care" for the floor plan question: the plan reader needs a
measured drawing and extracts nothing from them either way.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from reviewpulse.annotate.sheet_kind import ask_vlm, from_words, plan_bearing

SRC = {"chief_architect_austin": "data/real_plans/chief_architect_austin.pdf",
       "rebuildflorida_floorplans": "data/real_plans/rebuildflorida_floorplans.pdf",
       "millcreek_existing_proposed": "data/real_plans/millcreek_existing_proposed.pdf",
       "nola_sketch": "data/real_plans/nola_sketch.pdf"}
# (file, page) -> (acceptable kinds, shows a floor plan? None = don't care)
LABELS = {
    ("chief_architect_austin", 1): ({"cover_or_3d"}, False),
    ("chief_architect_austin", 2): ({"site_plan"}, False),
    ("chief_architect_austin", 3): ({"elevation"}, False),
    ("chief_architect_austin", 4): ({"elevation"}, False),
    ("chief_architect_austin", 5): ({"floor_plan"}, True),
    ("chief_architect_austin", 6): ({"floor_plan"}, True),
    ("chief_architect_austin", 7): ({"structural_plan"}, False),
    ("chief_architect_austin", 8): ({"ceiling_or_services_plan"}, False),
    ("chief_architect_austin", 9): ({"structural_plan"}, False),
    ("chief_architect_austin", 10): ({"structural_plan", "elevation", "section_or_detail"}, False),
    ("millcreek_existing_proposed", 1): ({"floor_plan"}, True),
    ("nola_sketch", 1): ({"sketch", "floor_plan"}, None),
    ("nola_sketch", 2): ({"sketch", "floor_plan"}, None),
    ("rebuildflorida_floorplans", 1): ({"cover_or_3d", "schedule_or_notes"}, False),
    ("rebuildflorida_floorplans", 2): ({"schedule_or_notes"}, False),
    ("rebuildflorida_floorplans", 3): ({"floor_plan", "structural_plan"}, True),
    ("rebuildflorida_floorplans", 4): ({"elevation"}, False),
    ("rebuildflorida_floorplans", 5): ({"section_or_detail", "elevation"}, False),
    ("rebuildflorida_floorplans", 6): ({"schedule_or_notes", "section_or_detail"}, False),
    ("rebuildflorida_floorplans", 7): ({"structural_plan", "floor_plan"}, False),
    ("rebuildflorida_floorplans", 8): ({"section_or_detail"}, False),
    ("rebuildflorida_floorplans", 9): ({"section_or_detail"}, False),
    ("rebuildflorida_floorplans", 10): ({"schedule_or_notes"}, False),
}


def big_text(pdf: str, page: int) -> str:
    p = pymupdf.open(pdf)[page - 1]
    spans = [s for b in p.get_text("dict")["blocks"] if "lines" in b for ln in b["lines"] for s in ln["spans"]]
    if not spans:
        return ""
    top = max(s["size"] for s in spans)
    return " ".join(s["text"] for s in spans if s["size"] >= 0.8 * top)


def main() -> None:
    old = {(r["file"].removesuffix(".pdf"), r["page"]): r for r in json.loads(Path("reports/real_plans/results.json").read_text())}
    rows = []
    for (name, page), (kinds, plan) in LABELS.items():
        png = Path(f"reports/real_plans/{name}_p{page}.png")
        v = ask_vlm(png)
        words = from_words(re.sub(r"\s+", " ", big_text(SRC[name], page)))
        was = (old.get((name, page)) or {}).get("result", {}) or {}
        rows.append({"page": f"{name[:10]} p{page}", "truth": sorted(kinds), "plan": plan, "vision": v and v["kind"],
                     "vision_plan": v and plan_bearing(v), "words": words, "old_rooms": was.get("rooms")})
    for r in rows:
        print(f"{r['page']:<16} truth {'/'.join(r['truth'])[:34]:<34} vision {str(r['vision'])[:24]:<24} "
              f"words {str(r['words'])[:22]:<22} old rooms {r['old_rooms']}")
    scored = [r for r in rows if r["plan"] is not None]

    def acc(pred):
        ok = sum(bool(pred(r)) == r["plan"] for r in scored)
        tp = sum(bool(pred(r)) and r["plan"] for r in scored)
        fp = sum(bool(pred(r)) and not r["plan"] for r in scored)
        fn = sum(not pred(r) and r["plan"] for r in scored)
        return f"correct {ok}/{len(scored)}  plan pages found {tp}/{tp + fn}  non-plan pages wrongly taken {fp}"

    print("\nfloor plan or not:")
    print("  vision, 'contains a floor plan' flag too:", acc(lambda r: r["vision_plan"]))
    print("  vision, main kind only :", acc(lambda r: r["vision"] == "floor_plan"))
    print("  title words  :", acc(lambda r: r["words"] == "floor_plan"))
    print("  before (rooms found => plan):", acc(lambda r: (r["old_rooms"] or 0) > 0))
    kinds_ok = sum(r["vision"] in r["truth"] for r in rows)
    print(f"\nexact kind (vision): {kinds_ok}/{len(rows)}")


if __name__ == "__main__":
    main()
