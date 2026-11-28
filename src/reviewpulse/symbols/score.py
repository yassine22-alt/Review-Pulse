"""Scoring a run against the truth of a generated drawing: recall, precision, placement IoU, label and room correctness."""

from __future__ import annotations

from dataclasses import dataclass, field


def iou(a, b) -> float:
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


@dataclass
class Score:
    n_truth: int = 0
    n_found: int = 0
    tp: int = 0                  # right place, right label
    mislabel: int = 0            # right place, wrong label
    fp: int = 0                  # nothing planted there
    fn: int = 0                  # planted, not found (or found with the wrong label)
    ious: list[float] = field(default_factory=list)
    room_ok: int = 0
    distractor_hits: int = 0     # false positives that sit on a distractor
    n_unlisted: int = 0          # planted symbols that are not in the legend
    unlisted_hits: int = 0       # of those, counted as a legend symbol (should be 0: the reject option)

    @property
    def recall(self) -> float:
        return self.tp / self.n_truth if self.n_truth else 1.0

    @property
    def precision(self) -> float:
        return self.tp / self.n_found if self.n_found else 1.0

    @property
    def mean_iou(self) -> float:
        return sum(self.ious) / len(self.ious) if self.ious else 0.0

    @property
    def room_acc(self) -> float:
        return self.room_ok / self.tp if self.tp else 1.0

    def add(self, o: Score) -> None:
        for k in ("n_truth", "n_found", "tp", "mislabel", "fp", "fn", "room_ok", "distractor_hits", "n_unlisted", "unlisted_hits"):
            setattr(self, k, getattr(self, k) + getattr(o, k))
        self.ious += o.ious


def score_view(truth_instances: list[dict], distractors: list[dict], dets: list, exemplars: list, placed_rooms: list,
               min_iou: float = 0.5, unlisted: list[dict] | None = None) -> Score:
    """dets are Detection objects, exemplars the list they index, placed_rooms the room id (or None) of each detection."""
    unlisted = unlisted or []
    s = Score(n_truth=len(truth_instances), n_found=len(dets), n_unlisted=len(unlisted))
    used = set()
    for d, room in zip(dets, placed_rooms, strict=True):
        best, bi = 0.0, None
        for i, t in enumerate(truth_instances):
            if i in used:
                continue
            v = iou(d.box, t["box"])
            if v > best:
                best, bi = v, i
        if bi is not None and best >= min_iou:
            used.add(bi)
            t = truth_instances[bi]
            if t["label"] in exemplars[d.exemplar].words:
                s.tp += 1
                s.ious.append(best)
                s.room_ok += int(room == t["room"])
            else:
                s.mislabel += 1
        else:
            s.fp += 1
            if any(iou(d.box, x["box"]) >= 0.5 for x in unlisted):
                s.unlisted_hits += 1
            if any(iou(d.box, x["box"]) > 0.2 for x in distractors):
                s.distractor_hits += 1
    s.fn = s.n_truth - s.tp
    return s


def run_synthetic(tmp_dir, seeds=range(6), method: str = "descriptor", n_symbols=(6, 8, 10, 12, 8, 12), scale_aware: bool = False,
                  band=None, **kw) -> tuple[Score, list]:
    """Generate one drawing per seed, run the finder through the real readers, bind to the true rooms, score. Returns the
    pooled score and the per-drawing (truth, SetResult) pairs."""
    from pathlib import Path

    import numpy as np  # noqa: F401

    from .bind import Room
    from .find import BAND
    from .run import run_pdf
    from .synth import make_pdf

    tot = Score()
    runs = []
    for i, seed in enumerate(seeds):
        path = Path(tmp_dir) / f"syn_{seed}.pdf"
        tr = make_pdf(path, seed=seed, n_symbols=n_symbols[i % len(n_symbols)], **kw)
        rooms = [Room(r["id"], r["polygon"], r["label"]) for r in tr.rooms]
        r = run_pdf(path, method=method, scale_aware=scale_aware, band=band or BAND, rooms_for=lambda s, v, rooms=rooms: rooms)
        if not r.views:
            tot.add(Score(n_truth=len(tr.instances), fn=len(tr.instances)))
            runs.append((tr, r))
            continue
        v = r.views[0]
        tot.add(score_view(tr.instances, tr.distractors, v.result.detections, r.exemplars, [p.room for p in v.placed], unlisted=tr.unlisted))
        runs.append((tr, r))
    return tot, runs
