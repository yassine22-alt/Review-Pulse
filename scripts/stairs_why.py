"""Why labelled real stairs are not found: run the finder on each missed instance alone and collect its trace."""
import copy, random
from collections import Counter, defaultdict
from pathlib import Path
from reviewpulse.ingest.svg_reader import extract_svg
from reviewpulse.perception.stairs import find_stairs
ROOT = Path("../Review-Pulse/reviewpulse/data/raw/floorplancad/FloorPlanCAD")
files = sorted(ROOT.glob("*/*.svg")); random.Random(5).shuffle(files)
k = 0; why = Counter(); alone_found = in_sheet_missed = 0
for f in files:
    if k >= 80: break
    if f.stat().st_size > 6_000_000 or 'semanticId="28"' not in f.read_text(encoding="utf-8", errors="ignore"): continue
    k += 1
    sheet = extract_svg(f, f.stem); det = {m for e in find_stairs(sheet, 0.1) for m in e.member_ids}
    inst = defaultdict(list)
    for p in sheet.primitives:
        g = p.prov.evidence.get("gt")
        if g and g["semantic"] == 28: inst[g["instance"]].append(p)
    for i, ps in inst.items():
        if any(p.id in det for p in ps): continue
        solo = copy.copy(sheet); solo.primitives = ps; tr = []
        if find_stairs(solo, 0.1, tr):
            alone_found += 1; why["found alone, lost among the other strokes of the sheet"] += 1
        else:
            why[(Counter(t.split(" (")[0] for t in tr).most_common(1) or [("too few parallel strokes", 0)])[0][0]] += 1
print("alone-found", alone_found); print(why.most_common())
