"""The pictures and questions of the visual search test (docs/progress/M35), made where the drawings are.

    python scripts/visual_tiles.py <folder of the PDFs> <out folder>

Writes one picture per tile and ``tasks.json``: the tiles (with the text written inside each), and per query the tiles of its
pool and which of them are right. The drawings are not in the repository and the output is not committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.interpreter import vision  # noqa: E402

KEYS = {"held_out": "benchmarks/vision_held_out.json", "older": "benchmarks/vision_presence.json"}
GRID = 3


def build(keys: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """(tiles, queries) from the keys alone: no picture is read here."""
    tiles, queries = [], []
    for name, key in keys.items():
        words = {q["id"].split(".", 1)[1]: q["what"] for a in key["areas"] for q in a["questions"] if name == "held_out"}
        unclear = set()                                       # (area id, the object's words)
        for qid in key.get("unclear", []):
            area, suffix = qid.split(".", 1)
            unclear.add((area, words[suffix]))
        found: dict[tuple, dict] = {}                          # (pdf, what) -> what is known about that query
        for a in key["areas"]:
            parts = [{"id": f"{name}/{a['id']}/{n}", "key": name, "pdf": a["pdf"], "page": a["page"], "area": a["id"],
                      "in_area": list(t), "on_page": list(vision.tile_page_box(a["box"], t))}
                     for n, t in enumerate(vision.tiles(GRID))]
            tiles += parts
            for q in a["questions"]:
                got = found.setdefault((a["pdf"], q["what"]), {"right": [], "cues": []})
                if q["present"] and (a["id"], q["what"]) not in unclear:
                    got["cues"].append(q.get("cue"))
                    got["right"] += [t["id"] for t in parts if any(vision.overlaps(t["in_area"], b) for b in q.get("boxes", []))]
        for (pdf, what), got in found.items():
            if not got["right"]:
                continue
            pool = [t["id"] for t in tiles if t["key"] == name and t["pdf"] == pdf and (t["area"], what) not in unclear]
            queries.append({"id": f"{name}/{pdf}/{what}", "key": name, "pdf": pdf, "what": what, "pool": pool,
                            "right": sorted(set(got["right"])),
                            "cue": "drawn" if all(c == "drawn" for c in got["cues"]) else "named"})
    return tiles, queries


def main() -> None:
    import pymupdf

    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    tiles, queries = build({n: json.loads((ROOT / f).read_text(encoding="utf-8")) for n, f in KEYS.items()})
    (args.out / "tiles").mkdir(parents=True, exist_ok=True)
    for t in tiles:
        t["file"] = "tiles/" + t["id"].replace("/", "_") + ".png"
        vision.render_area(args.pdfs / t["pdf"], t["page"], t["on_page"]).save(args.out / t["file"])
        with pymupdf.open(args.pdfs / t["pdf"]) as doc:
            page = doc[t["page"] - 1]
            r, box = page.rect, t["on_page"]
            clip = pymupdf.Rect(r.width * box[0], r.height * box[1], r.width * box[2], r.height * box[3])
            t["text"] = " ".join(page.get_text("text", clip=clip * page.derotation_matrix).split())
    (args.out / "tasks.json").write_text(json.dumps({"tiles": tiles, "queries": queries}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    for name in KEYS:
        mine = [q for q in queries if q["key"] == name]
        print(f"{name}: {sum(t['key'] == name for t in tiles)} tiles ({sum(t['key'] == name and bool(t['text']) for t in tiles)} "
              f"with text), {len(mine)} queries, {sum(q['cue'] == 'drawn' for q in mine)} drawn only")


if __name__ == "__main__":
    main()
