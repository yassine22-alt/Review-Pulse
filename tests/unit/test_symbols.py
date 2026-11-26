"""Symbols found by their legend: descriptor invariances, planted truth, metamorphic changes, the reject option, candidates."""

from __future__ import annotations

import math

import numpy as np
import pytest

from reviewpulse.ledger.candidate import Candidate
from reviewpulse.symbols import candidates, counts, describe, distance, signature_hash
from reviewpulse.symbols.primitives import Stroke
from reviewpulse.symbols.score import run_synthetic
from reviewpulse.symbols.synth import GLYPHS, WORDS


def glyph_strokes(g: int, theta=0.0, size=10.0, centre=(100.0, 100.0), mirror=False, polygons=False) -> list[Stroke]:
    out = []
    c = np.array(centre)
    rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    for op in GLYPHS[g]:
        if op[0] == "circle":
            n = 24 if polygons else 48
            a = np.linspace(0, 2 * math.pi, n + 1)
            p = np.stack([op[1] + op[3] * np.cos(a), op[2] + op[3] * np.sin(a)], axis=1)
            closed = True
        elif op[0] == "line":
            p, closed = np.array([op[1], op[2]], dtype=float), False
        else:
            p = np.array(op[1] + ([op[1][0]] if op[2] else []), dtype=float)
            closed = bool(op[2])
        if mirror:
            p = p * np.array([-1.0, 1.0])
        out.append(Stroke(p @ rot.T * size + c, bool(op[-1]) if op[0] != "line" else False, closed))
    return out


def test_descriptor_is_invariant():
    for g in range(len(GLYPHS)):
        base = describe(glyph_strokes(g))
        for kw in ({"theta": 1.1}, {"size": 25.0, "centre": (400.0, 30.0)}, {"mirror": True}, {"theta": 3.0, "size": 4.0}):
            assert distance(base, describe(glyph_strokes(g, **kw))) < 0.05, (g, kw)


def test_descriptor_tells_symbols_apart():
    ds = [describe(glyph_strokes(g)) for g in range(len(GLYPHS))]
    near = min(distance(ds[i], ds[j]) for i in range(len(ds)) for j in range(i + 1, len(ds)))
    assert near > 0.08


def test_hash_baseline_is_exact_only():
    a = glyph_strokes(0)
    assert signature_hash(a) == signature_hash(glyph_strokes(0, size=30.0, centre=(5.0, 5.0)))   # scale and move: same
    assert signature_hash(a) != signature_hash(glyph_strokes(0, theta=0.7))                      # a turn breaks it
    assert signature_hash(a) != signature_hash(glyph_strokes(0, polygons=True))                  # a recut circle breaks it
    assert signature_hash([]) is None


def test_planted_truth_recall_precision_and_rooms(tmp_path):
    t, _ = run_synthetic(tmp_path, seeds=range(3), n_symbols=(6, 9, 12))
    assert t.n_truth > 80
    assert t.recall >= 0.97 and t.precision >= 0.95
    assert t.mean_iou >= 0.9 and t.mislabel == 0
    assert t.room_acc >= 0.99


def test_descriptor_beats_the_hash_baseline(tmp_path):
    d, _ = run_synthetic(tmp_path, seeds=range(2))
    h, _ = run_synthetic(tmp_path, seeds=range(2), method="hash")
    assert d.recall > h.recall + 0.4
    d2, _ = run_synthetic(tmp_path, seeds=range(2), circles_as_polygons=True)
    h2, _ = run_synthetic(tmp_path, seeds=range(2), method="hash", circles_as_polygons=True)
    assert d2.recall >= 0.97 and h2.recall < 0.3


def test_symbols_not_in_the_legend_are_rejected(tmp_path):
    t, _ = run_synthetic(tmp_path, seeds=range(3), n_symbols=(10, 10, 10), legend_n=6)
    assert t.n_unlisted > 10
    assert t.unlisted_hits <= 1 and t.recall >= 0.95


def test_metamorphic_page_changes_keep_the_result(tmp_path):
    base, _ = run_synthetic(tmp_path, seeds=range(2))
    for kw in ({"page_scale": 0.5}, {"page_scale": 1.7}, {"shift": (60.0, -25.0)}, {"wall_touch": 0.6}):
        t, _ = run_synthetic(tmp_path, seeds=range(2), **kw)
        assert t.recall >= base.recall - 0.03 and t.precision >= base.precision - 0.03, kw
    # a turned page: the model puts it upright again, so the rooms of the upright drawing still hold
    for rot in (90, 180, 270):
        t, _ = run_synthetic(tmp_path, seeds=range(2), page_rotation=rot)
        assert t.recall >= base.recall - 0.03 and t.room_acc >= 0.99, rot


def test_changing_the_legend_symbol_moves_the_label(tmp_path):
    n = 6
    perm = (1, 0, 2, 3, 4, 5)       # the first two legend rows swap their drawn symbols
    t, runs = run_synthetic(tmp_path, seeds=range(2), n_symbols=(n,), legend_perm=perm)
    assert t.recall >= 0.97 and t.mislabel == 0 and t.precision >= 0.95
    tr, res = runs[0]
    lab = {e.label: e for e in res.exemplars}
    assert WORDS[0] in lab and WORDS[1] in lab
    # glyph 1 is now drawn in row 0, so instances of glyph 1 carry the words of row 0
    assert all(i["label"] == WORDS[0] for i in tr.instances if i["glyph"] == 1)


def test_candidates_are_typed_counts_with_a_source(tmp_path):
    t, runs = run_synthetic(tmp_path, seeds=[2], n_symbols=(6,))
    tr, res = runs[0]
    v = res.views[0]
    cands = candidates(v.placed, "A-101")
    assert cands and all(isinstance(c, Candidate) and c.kind == "inferred" and c.unit == "1" for c in cands)
    assert all("symbol matched to legend entry" in c.source and "A-101" in c.source for c in cands)
    assert all(0.05 <= c.score <= 0.95 for c in cands)
    per = counts(v.placed)
    assert sum(sum(r.values()) for r in per.values()) == len(v.placed)
    truth = {}
    for i in tr.instances:
        truth[(i["room"], i["label"])] = truth.get((i["room"], i["label"]), 0) + 1
    got = {(c.entity, c.words): c.value for c in cands}
    assert got == truth


def test_line_swatches_and_patterns_are_not_exemplars(tmp_path):
    from reviewpulse.drawingset.model import LegendEntry
    from reviewpulse.symbols.find import build_exemplars
    strokes = [Stroke(np.array([[0.0, 5.0], [60.0, 5.0]])), Stroke(np.array([[0.0, 0.0], [5.0, 5.0], [10.0, 0.0]]))]
    entries = [LegendEntry(0, "0.1", "WALL", (0.0, 4.0, 60.0, 6.0), 1, (0, 0, 100, 10)),
               LegendEntry(0, "0.1", "PEAK", (0.0, 0.0, 10.0, 5.0), 1, (0, 0, 100, 10)),
               LegendEntry(0, "0.1", "NOTHING", None, 0, (0, 0, 100, 10))]
    ex, rej = build_exemplars(entries, {0: strokes})
    assert [e.label for e in ex] == ["PEAK"]
    assert {i for i, _ in rej} == {0, 2}


@pytest.mark.parametrize("n", [6, 12])
def test_legend_sizes(tmp_path, n):
    t, _ = run_synthetic(tmp_path, seeds=[5], n_symbols=(n,))
    assert t.recall >= 0.95 and t.precision >= 0.95
