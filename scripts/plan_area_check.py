"""Score the room finder on a real drawing with no annotation, using the areas the drawing prints itself.

    python scripts/plan_area_check.py <plans.pdf> --pages 5,7 [--out reports/plan_area_check] [--json]

Many drawings print the area of each room ("288 SQ FT", "14,5 m2"). The reader keeps that number as `stated_area_m2`. If the
rooms were found correctly, the measured area agrees with it. This script runs one page at a time through the plan
analysis and reports, per sheet: scale (and how it was found), rooms found, rooms that carry a printed area, and how many
of those agree within 25% and within 50%. It also lists printed areas that no room carries (rooms that were not found).
Each page is also drawn to a picture for a person to look at. Nothing is tuned per document.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pymupdf

from reviewpulse import pipeline


def score(building: dict) -> dict:
    rooms = building["rooms"]
    with_area = [r for r in rooms if r.get("stated_area_m2") and r.get("area_m2")]
    ratios = [r["area_m2"] / r["stated_area_m2"] for r in with_area]
    texts = building["sheet"]["texts"] if "sheet" in building else []
    printed = [t for t in texts if t.get("kind") == "area" and t.get("value")]
    inferred = sum(1 for r in rooms if r["prov"]["evidence"].get("boundary") == "inferred_from_labels")
    return {"rooms": len(rooms), "inferred_boundary": inferred, "with_printed_area": len(with_area),
            "printed_area_texts": len({(round(t["bbox"][0]), round(t["bbox"][1])) for t in printed}),
            "within_25pct": sum(0.75 <= x <= 1.25 for x in ratios), "within_50pct": sum(0.5 <= x <= 1.5 for x in ratios),
            "ratios": [round(x, 2) for x in sorted(ratios)],
            "largest_room_m2": max((r["area_m2"] for r in rooms if r.get("area_m2")), default=None)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", required=True, help="1-based page numbers, comma separated")
    ap.add_argument("--out", default="reports/plan_area_check")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(args.pdf)
    rows = []
    for n in [int(x) for x in args.pages.split(",")]:
        with tempfile.TemporaryDirectory() as tmp:
            one = pymupdf.open()
            one.insert_pdf(doc, from_page=n - 1, to_page=n - 1)
            single = Path(tmp) / f"{Path(args.pdf).stem}_p{n}.pdf"
            one.save(single)
            rd = pipeline.inspect(single, Path(tmp) / "runs", run_id="r")
            pipeline.extract(rd)
            pipeline.build(rd)
            b = json.loads(next(Path(rd).glob("building_*.json")).read_text(encoding="utf-8"))
            sc = json.loads(next(Path(rd).glob("scale_report_*.json")).read_text(encoding="utf-8"))
            png = next(Path(rd).glob("rooms_*.png"), None)
            if png:
                (out / f"{single.stem}_rooms.png").write_bytes(png.read_bytes())
        s = score(b)
        s.update(page=n, scale=b["sheet"]["scale"]["method"], scale_notes=sc.get("notes", [])[:2],
                 warnings=[w[:100] for w in (b["sheet"].get("warnings") or [])][:4])
        rows.append(s)
        print(f"p{n}: scale {s['scale']}; {s['rooms']} rooms ({s['inferred_boundary']} cut from labels); "
              f"{s['with_printed_area']} with printed area of {s['printed_area_texts']}; "
              f"within 25%: {s['within_25pct']}, within 50%: {s['within_50pct']}; largest {s['largest_room_m2']} m2",
              flush=True)
        print("   ratios measured/printed:", s["ratios"], flush=True)
    (out / f"{Path(args.pdf).stem}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
