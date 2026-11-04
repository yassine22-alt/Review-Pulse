"""T4 regression snapshots: fixed plans, stored summaries, compared within tolerances.

    pytest tests/golden/test_snapshots.py                    # compare
    pytest tests/golden/test_snapshots.py --snapshot-update  # rewrite, then review the diff in the PR

A summary holds element counts per class, room areas (sorted), the room-graph edge count, the scale
and the set of (rule, verdict) pairs. Counts and verdicts must match exactly; areas within
max(2%, 0.2 m2); scale within 0.5%.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

SNAP = Path(__file__).parent / "snapshots"
CASES = {
    "synth_clean_dxf": ("make", dict(seed=101), "dxf"),
    "synth_clean_pdf": ("make", dict(seed=101), "pdf"),
    "synth_bath_route_pdf": ("make", dict(seed=102, errors=("topo_exit_via_bath",)), "pdf"),
    "synth_door_narrow_dxf": ("make", dict(seed=103, errors=("metric_door_narrow",)), "dxf"),
    "synth_chain_pdf": ("make", dict(seed=104, errors=("cons_chain_off",)), "pdf"),
    "synth_rotated90_pdf": ("make", dict(seed=105, rotate=90, errors=("coord_swing_overlap",)), "pdf"),
    "random_fill_none_dxf": ("rand", dict(seed=801, scheme="none", wall_style="filled", door_style="segments",
                                          angle=0.0, units="mm", clutter=True), "dxf"),
    "random_hatch_numeric_pdf": ("rand", dict(seed=802, scheme="numeric", wall_style="hatched", door_style="block",
                                              angle=17.0, units="m", clutter=True), "pdf"),
    "random_bulge_fr_pdf": ("rand", dict(seed=803, scheme="fr", wall_style="polylines", door_style="bulge",
                                         angle=-33.0, units="mm", clutter=False), "pdf"),
    "random_lines_aia_dxf": ("rand", dict(seed=804, scheme="aia", wall_style="lines", door_style="arc_only",
                                          angle=90.0, units="m", clutter=True), "dxf"),
}


def summarise(kind: str, kw: dict, fmt: str, work: Path) -> dict:
    from reviewpulse.cli import DEFAULT_PACK
    from reviewpulse.engine.run import run
    from reviewpulse.eval.cli import _model_from
    from reviewpulse.rules.schema import load_pack
    from reviewpulse.synth.make_plan import make_plan
    from reviewpulse.synth.random_plan import random_plan

    paths = make_plan(work, png=False, **kw) if kind == "make" else random_plan(work, **kw)
    m = _model_from(paths[fmt])
    findings = run(m, load_pack(DEFAULT_PACK))
    return {
        "elements": dict(sorted(Counter(e.cls for e in m.elements).items())),
        "rooms_m2": sorted(round(r.area_m2 or 0.0, 2) for r in m.rooms),
        "edges": len(m.edges),
        "scale": m.sheet.scale.metres_per_unit,
        "verdicts": sorted(f"{f.rule_id}:{f.verdict}" for f in {(f.rule_id, f.verdict): f for f in findings}.values()),
    }


def _compare(old: dict, new: dict) -> list[str]:
    diffs = []
    if old["elements"] != new["elements"]:
        diffs.append(f"elements {old['elements']} -> {new['elements']}")
    if old["edges"] != new["edges"]:
        diffs.append(f"edges {old['edges']} -> {new['edges']}")
    if len(old["rooms_m2"]) != len(new["rooms_m2"]):
        diffs.append(f"room count {len(old['rooms_m2'])} -> {len(new['rooms_m2'])}")
    else:
        for a, b in zip(old["rooms_m2"], new["rooms_m2"]):
            if abs(a - b) > max(0.02 * a, 0.2):
                diffs.append(f"room area {a} -> {b}")
    if (old["scale"] is None) != (new["scale"] is None) or (
            old["scale"] and abs(old["scale"] - new["scale"]) > 0.005 * old["scale"]):
        diffs.append(f"scale {old['scale']} -> {new['scale']}")
    if old["verdicts"] != new["verdicts"]:
        diffs.append(f"verdicts -{sorted(set(old['verdicts']) - set(new['verdicts']))} "
                     f"+{sorted(set(new['verdicts']) - set(old['verdicts']))}")
    return diffs


@pytest.mark.parametrize("name", list(CASES))
def test_snapshot(name, tmp_path, request):
    kind, kw, fmt = CASES[name]
    new = summarise(kind, kw, fmt, tmp_path)
    path = SNAP / f"{name}.json"
    if request.config.getoption("--snapshot-update") or not path.exists():
        SNAP.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(new, indent=1), encoding="utf-8")
        if not request.config.getoption("--snapshot-update"):
            pytest.skip(f"snapshot created: {path.name}")
        return
    old = json.loads(path.read_text(encoding="utf-8"))
    diffs = _compare(old, new)
    assert not diffs, f"{name} changed (rerun with --snapshot-update if intended): " + "; ".join(diffs)
