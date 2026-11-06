"""Stairs found from geometry alone, scored against FloorPlanCAD's own stair labels (semantic id 28)."""
import json, random, sys, time
from collections import defaultdict
from pathlib import Path
from reviewpulse.ingest.svg_reader import extract_svg
from reviewpulse.perception.stairs import find_stairs

ROOT = Path("../Review-Pulse/reviewpulse/data/raw/floorplancad/FloorPlanCAD")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
files = sorted(ROOT.glob("*/*.svg"))
random.Random(5).shuffle(files)
with_s, without = [], []
for f in files:
    if len(with_s) >= N and len(without) >= N: break
    if f.stat().st_size > 6_000_000: continue
    has = 'semanticId="28"' in f.read_text(encoding="utf-8", errors="ignore")
    (with_s if has else without).append(f) if (len(with_s) < N if has else len(without) < N) else None

def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)

def area(a): return max(0, a[2]-a[0]) * max(0, a[3]-a[1])

res = {"gt_inst": 0, "found": 0, "det": 0, "det_ok": 0, "files_with": 0, "fp_files": 0, "fp_det": 0, "secs": 0.0}
pitches = []
for kind, group in (("with", with_s), ("without", without)):
    for f in group:
        t0 = time.time()
        try:
            sheet = extract_svg(f, f.stem)
            st = find_stairs(sheet, 0.1)
        except Exception as e:
            print("ERR", f.name, type(e).__name__, str(e)[:80]); continue
        res["secs"] += time.time() - t0
        pitches += [e.prov.evidence["tread_depth_m"] for e in st]
        if kind == "without":
            res["fp_det"] += len(st); res["fp_files"] += bool(st); continue
        inst = defaultdict(set)
        for p in sheet.primitives:
            g = p.prov.evidence.get("gt")
            if g and g["semantic"] == 28:
                inst[g["instance"]].add(p.id)
        allgt = set().union(*inst.values()) if inst else set()
        detected = set().union(*[set(e.member_ids) for e in st]) if st else set()
        res["gt_inst"] += len(inst); res["det"] += len(st)
        res["found"] += sum(len(v & detected) >= 1 for v in inst.values())
        res["cover25"] = res.get("cover25", 0) + sum(len(v & detected) >= 0.25 * len(v) for v in inst.values())
        res["det_ok"] += sum(len(set(e.member_ids) & allgt) >= 0.5 * len(e.member_ids) for e in st)
        res["files_with"] += 1
print(json.dumps(res, indent=1))
import statistics
print("files with stairs", len(with_s), "without", len(without))
print("instances with >=25%% of their lines covered: %d/%d" % (res.get("cover25",0), res["gt_inst"]))
print("stair instances found %d/%d = %.0f%%" % (res["found"], res["gt_inst"], 100*res["found"]/max(1,res["gt_inst"])))
print("detections on stair files that touch a labelled stair %d/%d = %.0f%%" % (res["det_ok"], res["det"], 100*res["det_ok"]/max(1,res["det"])))
print("files WITHOUT stairs with any detection %d/%d, detections %d" % (res["fp_files"], len(without), res["fp_det"]))
if pitches: print("tread depth median %.2f m, 10-90%% %.2f-%.2f" % (statistics.median(pitches), *statistics.quantiles(pitches, n=10)[0:9:8]))
