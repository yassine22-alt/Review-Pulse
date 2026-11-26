"""Audit of symbols found by their legend.

    python scripts/symbols_audit.py synthetic [--json out.json]
    python scripts/symbols_audit.py real data/real_plans/chief_architect_austin.pdf [more.pdf] --crops DIR [--json out.json]

synthetic  planted truth (recall, precision, placement IoU, room binding) under turns, sizes, line weights, distractors,
           near misses, symbols against walls, a recut circle; metamorphic page changes; the reject option; and the exact
           signature hash baseline on the same drawings.
real       counts per legend symbol on a real set, 40 detections drawn as crops on contact sheets (PNG, to be read and
           graded by a person), and a cross check against counts that notes state in words.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import pymupdf
import yaml

from reviewpulse.symbols.find import BAND
from reviewpulse.symbols.run import run_pdf
from reviewpulse.symbols.score import run_synthetic

CLASSES = yaml.safe_load((Path(__file__).parent.parent / "src/reviewpulse/symbols/classes.yaml").read_text(encoding="utf-8"))

CONDITIONS = [
    ("base (free turns, sizes 0.85-1.25, weights 0.5-1.6)", {}),
    ("circles cut as polygons", {"circles_as_polygons": True}),
    ("symbols against walls", {"wall_touch": 0.6}),
    ("dense distractors (8 per room)", {"n_distractors": 8}),
    ("thin lines 0.1-0.3", {"line_weights": (0.1, 0.3)}),
    ("heavy lines 2-4", {"line_weights": (2.0, 4.0)}),
    ("symbols 1.5x the legend size", {"instance_scale": 1.5}),
    ("symbols 1.6x the legend size", {"instance_scale": 1.6}),
    ("symbols 0.6x the legend size", {"instance_scale": 0.6}),
    ("symbols 0.4x the legend size", {"instance_scale": 0.4}),
    ("page scaled 0.5", {"page_scale": 0.5}),
    ("page scaled 1.7", {"page_scale": 1.7}),
    ("page moved", {"shift": (60.0, -25.0)}),
    ("page turned 90", {"page_rotation": 90}),
    ("page turned 180", {"page_rotation": 180}),
    ("page turned 270", {"page_rotation": 270}),
    ("legend swaps two symbols", {"legend_perm": (1, 0, 2, 3, 4, 5, 6, 7), "n_symbols": (8,)}),
    ("4 of 10 symbols not in the legend", {"legend_n": 6, "n_symbols": (10,)}),
]


def row(name, t):
    return {"condition": name, "truth": t.n_truth, "found": t.n_found, "tp": t.tp, "mislabel": t.mislabel, "fp": t.fp,
            "fn": t.fn, "recall": round(t.recall, 3), "precision": round(t.precision, 3), "iou": round(t.mean_iou, 3),
            "room_acc": round(t.room_acc, 3), "on_distractor": t.distractor_hits, "unlisted": t.n_unlisted,
            "unlisted_counted": t.unlisted_hits}


def synthetic(seeds=range(8)):
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, kw in CONDITIONS:
            kw = dict(kw)
            for method in ("descriptor", "hash"):
                t, _ = run_synthetic(tmp, seeds=seeds, method=method, **kw)
                r = row(name, t)
                r["method"] = method
                out.append(r)
                print(f"{method:10s} {name:52s} truth {t.n_truth:3d} R {t.recall:.3f} P {t.precision:.3f} iou {t.mean_iou:.3f} "
                      f"room {t.room_acc:.3f} fp {t.fp} mislabel {t.mislabel} unlisted {t.unlisted_hits}/{t.n_unlisted}", flush=True)
        t, _ = run_synthetic(tmp, seeds=seeds, band=(0.35, 3.2), instance_scale=1.6)
        print(f"wide band 0.35-3.2 at 1.6x: R {t.recall:.3f} P {t.precision:.3f}")
        out.append({**row("wide band 0.35-3.2, symbols 1.6x", t), "method": "descriptor"})
    return out


# ---- real sets -----------------------------------------------------------------------------------------------------

def stated_counts(pdf: Path) -> dict[str, list[tuple[int, str, int]]]:
    """Counts a note states in words ("(6) smoke alarms", "six exhaust fans"): class -> [(count, line, page)]."""
    words = CLASSES["count_words"]["words"]
    num = r"(\d{1,3}|" + "|".join(words) + r")"
    out: dict[str, list] = {}
    doc = pymupdf.open(str(pdf))
    for pno, page in enumerate(doc):
        text = " ".join(page.get_text().split())
        for cls, spec in CLASSES["classes"].items():
            for pat in spec["note"]:
                for m in re.finditer(r"(?<![\w/.-])\(?" + num + r"\)?\s*(?:x\s*)?(?:new\s+|hard\s*wired\s+|interconnected\s+)*" + pat, text, re.I):
                    v = m.group(1).lower()
                    n = int(v) if v.isdigit() else words[v]
                    out.setdefault(cls, []).append((n, text[max(0, m.start() - 40):m.end() + 40], pno))
    return out


def class_of(label: str) -> str | None:
    for cls, spec in CLASSES["classes"].items():
        if any(re.search(p, label, re.I) for p in spec["legend"]):
            return cls
    return None


def contact_sheets(res, pdf: Path, out_dir: Path, n: int = 40, per_sheet: int = 8) -> list[dict]:
    """40 detections spread over the symbols (round robin, nearest first), each drawn with its legend symbol beside it."""
    doc = pymupdf.open(str(pdf))
    by_ex: dict[int, list] = {}
    for vr in res.views:
        for p in vr.placed:
            by_ex.setdefault(p.exemplar.id, []).append((vr, p))
    for v in by_ex.values():
        v.sort(key=lambda t: t[1].detection.dist)
    chosen = []
    i = 0
    while len(chosen) < n and any(by_ex.values()):
        for k in sorted(by_ex):
            if by_ex[k] and len(chosen) < n:
                # alternate nearest and furthest so that the sample is not only the easy ones
                chosen.append(by_ex[k].pop(0 if i % 2 == 0 else -1))
        i += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = []
    for s0 in range(0, len(chosen), per_sheet):
        sheet = pymupdf.open()
        pg = sheet.new_page(width=1200, height=720)
        for j, (vr, p) in enumerate(chosen[s0:s0 + per_sheet]):
            no = s0 + j + 1
            col, rw = j % 4, j // 4
            x, y = 10 + col * 295, 10 + rw * 355
            page = doc[p.sheet]
            b = p.detection.box
            m = max(b[2] - b[0], b[3] - b[1], 6.0) * 1.8
            clip = pymupdf.Rect(b[0] - m, b[1] - m, b[2] + m, b[3] + m)
            pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(150 / max(clip.width, 1), 150 / max(clip.width, 1)) if clip.width < 100 else pymupdf.Matrix(3, 3))
            ex = p.exemplar
            lpage = doc[ex.sheet]
            eb = ex.box
            em = max(eb[2] - eb[0], eb[3] - eb[1]) * 0.6 + 2
            lclip = pymupdf.Rect(eb[0] - em, eb[1] - em, eb[2] + em, eb[3] + em)
            lpix = lpage.get_pixmap(clip=lclip, matrix=pymupdf.Matrix(120 / max(lclip.width, 1), 120 / max(lclip.width, 1)))
            pg.insert_image(pymupdf.Rect(x, y + 40, x + 130, y + 170), pixmap=lpix, keep_proportion=True)
            pg.insert_image(pymupdf.Rect(x + 135, y + 40, x + 285, y + 190), pixmap=pix, keep_proportion=True)
            pg.insert_text((x, y + 14), f"#{no} {ex.label[:34]}", fontsize=10)
            pg.insert_text((x, y + 28), f"d={p.detection.dist:.3f} tau={p.detection.tau:.2f} s{p.sheet} v{vr.view}", fontsize=8)
            pg.insert_text((x, y + 205), "left: legend symbol   right: detection", fontsize=7)
            meta.append({"no": no, "label": ex.label, "sheet": p.sheet, "view": vr.view, "dist": round(p.detection.dist, 3),
                         "box": [round(v, 1) for v in b]})
        pg.get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(str(out_dir / f"{pdf.stem}_sheet{s0 // per_sheet + 1}.png"))
    (out_dir / f"{pdf.stem}_sample.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def real(pdf: Path, crops: Path | None, pages=None):
    t0 = time.time()
    res = run_pdf(pdf, "descriptor", pages=pages)
    t1 = time.time()
    hres = run_pdf(pdf, "hash", pages=pages)
    print(f"\n== {pdf.name}: legend rows {len(res.drawing_set.legend)}, exemplars {len(res.exemplars)} "
          f"(rejected rows {len(res.rejected)}), plan views searched {len(res.views)}, {t1 - t0:.0f} s")
    from collections import Counter
    print("rejected reasons:", dict(Counter(r.split(',')[0][:40] for _, r in res.rejected)))
    per = {}
    for vr in res.views:
        for p in vr.placed:
            per.setdefault(p.exemplar.label, Counter())[vr.sheet] += 1
    hper = Counter()
    for vr in hres.views:
        for p in vr.placed:
            hper[p.exemplar.label] += 1
    rows = []
    for e in res.exemplars:
        c = per.get(e.label, Counter())
        rows.append({"symbol": e.label, "legend_sheet": e.sheet, "tau": round(e.tau, 3), "found": sum(c.values()),
                     "sheets": len(c), "hash_found": hper.get(e.label, 0), "class": class_of(e.label)})
        print(f"  {e.label[:46]:46s} tau {e.tau:.2f} found {sum(c.values()):4d} on {len(c):2d} sheets, hash {hper.get(e.label, 0)}")
    print(f"  ambiguous candidates {sum(len(v.result.ambiguous) for v in res.views)}, "
          f"not in the legend {sum(v.result.n_not_in_legend for v in res.views)}, "
          f"detections {sum(len(v.result.detections) for v in res.views)} (hash {sum(len(v.result.detections) for v in hres.views)})")
    stated = stated_counts(pdf)
    cross = []
    for cls, items in stated.items():
        got_syms = [r for r in rows if r["class"] == cls]
        for n, line, pno in items:
            cross.append({"class": cls, "stated": n, "page": pno, "line": line, "found_by_symbol": {r["symbol"]: r["found"] for r in got_syms}})
            print(f"  STATED {cls} = {n} (page {pno}): ...{line}...  symbols of the class found: {[(r['symbol'], r['found']) for r in got_syms]}")
    meta = contact_sheets(res, pdf, crops) if crops else []
    return {"pdf": pdf.name, "rows": rows, "cross": cross, "sample": meta, "seconds": round(t1 - t0), "rejected": len(res.rejected),
            "exemplars": len(res.exemplars), "views": len(res.views)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["synthetic", "real"])
    ap.add_argument("pdfs", nargs="*")
    ap.add_argument("--crops", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    out = synthetic() if a.mode == "synthetic" else [real(Path(p), a.crops) for p in a.pdfs]
    if a.json:
        a.json.write_text(json.dumps({"band": BAND, "result": out}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
