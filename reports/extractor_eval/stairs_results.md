# Stair finder: measured results (November 2026)

Finder: `src/reviewpulse/perception/stairs.py`. Scripts: `scripts/stairs_synth.py`, `scripts/stairs_eval.py`,
`scripts/stairs_calibrate.py`. Geometry only: no layer names, no text, no labels.

## Against synthetic flights with known truth (200 flights, random mix of styles and clutter)

Styles drawn at random: treads drawn twice (edge and nosing), treads broken in pieces, side rails, a centre line, a
second flight beside the first, any angle, drawing units from 1 mm to 0.1 m, endpoint noise up to 5 mm, and clutter
(wall pairs, hatching, periodic grids, uneven parallel strokes).

| Measure | Result |
|---|---|
| Flights found | 195 of 200 (98%) |
| Tread depth error | median 0.00 cm, 95th percentile 0.05 cm, largest 0.08 cm |
| Error inside 2 reported standard errors | 195 of 195 |
| Tread count exactly right | 190 of 195 |
| True step count inside the reported range | 195 of 195 |
| Marked trusted (110 flights) with a depth off by more than 1 cm | 0 |
| A false stair on 200 drawings with clutter and no stair | 6 (3%) |

## Against FloorPlanCAD labels (150 drawings with stairs, 150 without)

Labels are used only to score and to fit the confidence model, never to find stairs.

| Measure | Result |
|---|---|
| Labelled stairs with at least one line found | 151 of 264 (57%) |
| Detections where at least half of the lines belong to a labelled stair | 169 of 191 (88%) |
| Drawings without stairs with any detection | 18 of 150 (12%); the look-alikes are escalators, tables and wall grids |
| Why labelled stairs are missed (80 drawings, 61 misses) | 23 have too few parallel strokes (tick marks, curves); 20 are found when drawn alone but lost among the other strokes of the sheet; 12 are not significant (short flights); 4 have texture between the treads; 2 have treads of unequal length |

Tread depth and width on real drawings could not be checked: FloorPlanCAD says which lines are a stair, not how deep the
treads are. Median detected tread depth is 0.28 m, which is a normal value.

## Confidence model

Five numbers from the finder's own evidence (significance, tread count, distance of the pitch from a usual tread,
plausible width, fit error), a logistic model fitted on 212 detections from 360 drawings and checked on 140 detections
from drawings it never saw (held-out Brier score 0.055; always answering with the base rate gives 0.156).

| Predicted probability | Detections | Actually real |
|---|---|---|
| below 0.5 | 21 | 5% |
| 0.5 to 0.8 | 12 | 67% |
| 0.8 to 0.9 | 39 | 92% |
| 0.9 to 0.97 | 68 | 100% |

Keeping detections of 0.8 or more keeps 107 of 140 and 97% of them are real. The fit comes from one dataset and may need
refitting for other drawing styles (`scripts/stairs_calibrate.py`).
