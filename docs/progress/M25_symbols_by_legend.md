# M25: symbols found by their legend, on vector drawings (step 6 of the general plan)

This note is for someone new to the project. It says what I built, how I measured it, and where it fails. All code is new, in
`src/reviewpulse/symbols/`; no existing file was edited. Numbers come from `python scripts/symbols_audit.py synthetic` and
`python scripts/symbols_audit.py real <pdf> --crops DIR`, and from `tests/unit/test_symbols.py` (12 tests, passing).
No model is called anywhere in this step: the vision model scored 0 of 43 on locating legend symbols (plan, section 11), so
on vector sheets the shapes themselves are matched.

## What it does

1. **Exemplars.** Each legend entry of the drawing set model carries a box for its drawn symbol (`symbol_bbox`) and its words.
   The vector strokes inside the box are the exemplar. A stroke is a chain of path items that follow each other end to end
   (`primitives.py`); curves are flattened. A legend row that shows several symbols for words like "A / B / C" is split into
   groups of strokes, and the groups, left to right, take the parts of the words, when the counts agree. Entries that are not
   point symbols are refused with a reason: line swatches and hatches (aspect over 5), boxes with more than 60 strokes
   (patterns, or a box that swallowed neighbouring rows), sizes outside 3 to 90 points, no box.
2. **Descriptor** (`descriptor.py`). Strokes are simplified (Douglas-Peucker, 0.8% of the box diagonal, which removes noise and
   extra cut points), resampled at equal arc length steps (64 points), and described relative to their centroid and RMS radius:
   a soft histogram over (distance between two samples, angle between their tangents), a radial histogram, five Fourier
   magnitudes of the ink around the centroid, and a type block (share of the turning in corners and in smooth curves, total
   turning, filled share, closed share, aspect, ink amount). It does not change with translation, scale, rotation, mirroring or
   how a curve was cut (tested). The vector itself is the deterministic embedding. I did not add a hash index on top of it.
3. **Finding** (`find.py`). In each plan view, small strokes (long ones such as walls are left out first, so a symbol against a
   wall is a group of its own) are grouped by connected boxes at three gaps (0, 6%, 15% of the exemplar size). Groups whose box
   has the exemplar's size within a band of 0.5x to 2x are candidates. Each is compared with every exemplar; the nearest is the
   label if within that exemplar's threshold, otherwise it is "not in the legend" and dropped. A candidate whose second nearest
   exemplar is within 0.02 is ambiguous and not counted. Overlapping candidates are thinned, nearest first.
   The threshold of each exemplar is calibrated on the legend alone: the 95th percentile of the distance to 24 copies of it
   (turned, mirrored, rescaled 0.7 to 1.4, recut, jittered by 0.3% of its size), times 1.25, capped at half the distance to
   the nearest other exemplar, between 0.04 and 0.30.
4. **Rooms and facts** (`bind.py`). A symbol belongs to the room polygon (page points) that contains the centre of its box;
   outside every room it belongs to the view only. Counts per room and per view come out as `Candidate`s of
   `ledger/candidate.py` (imported, not edited): entity the room (or `view:<id>`), fact `count_<legend words>`, kind
   `inferred`, source "symbol matched to legend entry 'X' on sheet S ...", score from the match distance (a ranking, not a
   calibrated probability).

The baseline is the exact path signature: the strokes of a group moved to its corner, scaled by its larger side, every vertex
rounded to 1/16, hashed. Only drawings that agree vertex by vertex share a hash. Same candidates, same exemplars.

## Measured on drawings with the truth known

`synth.py` draws a legend of 6 to 12 symbols and a plan of nine rooms with pymupdf shapes, plants 3 to 6 instances of each
symbol at random places, free turns (half of them multiples of 90 degrees), sizes 0.85 to 1.25 of the legend, line weights 0.5
to 1.6, plus three distractors per room out of: door swings, toilets, sinks, columns, plain circles, counters with a line,
dimension ticks, and three near misses (a circle with a plus and diagonals, a square with a plus, a triangle with a dot). The
drawing then goes through the real readers (`build_drawing_set`, legend, views). 8 drawings per condition; a detection is
right when its box overlaps the planted one by at least 0.5 and the label is right. Last run (eight seeds):

| Condition | Truth | Recall (descriptor / hash) | Precision | Mean IoU | Room right |
| --- | --- | --- | --- | --- | --- |
| base | 289 | 1.000 / 0.315 | 1.000 | 1.000 | 1.000 |
| circles cut as polygons instead of curves | 289 | 1.000 / 0.052 | 1.000 | 1.000 | 1.000 |
| symbols against walls | 320 | 1.000 / 0.300 | 1.000 | 1.000 | 1.000 |
| 8 distractors per room | 325 | 1.000 / 0.302 | 1.000 | 1.000 | 1.000 |
| thin lines (0.1 to 0.3) / heavy lines (2 to 4) | 289 | 1.000 / 0.315 | 1.000 | 1.000 | 1.000 |
| page scaled 0.5 / 1.7, moved, turned 90, 180, 270 | 289 | 1.000 / 0.315 | 1.000 | 1.000 | 1.000 |
| legend swaps the drawn symbols of two rows (labels must follow) | 271 | 1.000 / 0.325 | 1.000, no wrong label | 1.000 | 1.000 |
| 4 of 10 planted symbols not in the legend | 203 listed, 129 unlisted | 1.000 / 0.404 | 1.000; 0 of 129 unlisted counted | 1.000 | 1.000 |
| symbols 1.5x the legend size | 308 | 0.945 / 0.334 | 1.000 | 1.000 | 1.000 |
| symbols 1.6x the legend size | 296 | 0.905 / 0.361 | 1.000 | 1.000 | 1.000 |
| symbols 0.6x the legend size | 294 | 0.993 / 0.303 | 1.000 | 1.000 | 1.000 |
| symbols 0.4x the legend size | 298 | 0.107 / 0.000 | 1.000 | 1.000 | 1.000 |
| symbols 1.6x, band widened to 0.35 to 3.2 | | 1.000 | 1.000 | | |

Reading it plainly:

* The hash baseline stays at about 0.3 recall because it needs the vertices to agree, which holds only for part of the instances; I did not break down which. It is 0.05 when circles are cut
  differently. The general method wins on every row, with no loss in precision, so I keep it.
* IoU is 1.0 because the generated shapes are the same strokes as the legend; a real set will not be this clean. These drawings
  are easy in that way and I do not claim the real numbers follow them.
* Symbols outside the 0.5x to 2x band are not looked for (0.4x: 0.107 recall). Widening the band recovers 1.6x on these
  drawings at no cost in precision, but I did not run the wide band on every condition, so the default stays 0.5 to 2.
  `run_pdf(scale_aware=True)` moves the band by legend scale over view scale when both are known; the generated drawings give
  the legend no scale, so I did not measure that option.
* An earlier version of the descriptor counted a circle with four spokes as a "ceiling fan" (an asterisk of three lines)
  because part of a bigger symbol matched a smaller exemplar, and a hexagon as a triangle because the calibration was too
  loose (turning classes flipped under 1% jitter). Both are fixed by simplifying strokes first and building the type block from
  turning mass; the test of unlisted symbols now passes (it failed at 12 of 48 before). A part of a larger symbol can still
  match a smaller exemplar when its shape is close: there is no rule against it.
* Room binding was tested against the true room rectangles, not against rooms detected by the pipeline.

## Measured on real sets

**This part is unfinished.** The disk of the laptop became full (0 bytes free) while the real runs were going, so the 40
crop reading, the Florida run and the final Chief run did not complete. What I have, from a first complete run on
`chief_architect_austin.pdf` (before rows with several symbols were split):

* 96 legend rows gave 9 exemplars; 84 rows were refused (19 line swatches or hatches, 4 without a box, about 45 with more
  than 60 strokes, about 16 outside the size band). The legend boxes of this set are mostly wrong (they cover several rows or
  outlined text), so few exemplars are usable. This is a loss of the legend reading, not of the matcher.
* 18 detections in 36 plan views with the descriptor, 7 with the exact hash (the hash finds the same 7 "fiber cement panel"
  boxes of one elevation sheet). 1213 candidates were rejected as not in the legend. None of the detections is graded: I did
  not read them.
* Stated count cross check: the only count a note gives is "provide one smoke detector and carbon monoxide detector in each
  room" (page 18), which is per room, not a number, and the set has no smoke detector exemplar, so there is nothing to
  compare. No agreement figure can be claimed.
* After this run I added the splitting of rows such as "SMOKE DETECTOR / THERMOSTAT / GAS" into one exemplar per symbol. On
  the electrical legend page it gave 11 exemplars (DW, RA, CD, CW, C5, TV, cook hood, washer, dryer, wall oven, switch) and no
  detection on that page's three plan views. Not graded either.

To finish: free disk space, then run `python scripts/symbols_audit.py real data/real_plans/chief_architect_austin.pdf
data/real_plans/rebuildflorida_floorplans.pdf --crops <dir>`; it writes contact sheets of 40 detections (legend symbol left,
detection right) and a JSON file, to be read and graded right, partial or wrong. Fill this section with that grading.


## Limits and losses (all of them)

* **Raster and outlined symbols are out of scope this round.** A legend symbol that is an image, or a sheet that is a scan,
  has no strokes; nothing is found and nothing is claimed. A second arm (crop the legend symbol, match crops, with a
  vision model only as a chooser among options) is the next step and is not built.
* Legend symbol boxes come from the drawing set model and are often wrong on real legends (boxes that cover several rows,
  outlined text counted as strokes). I did not edit that reader. Entries with more than 60 strokes are refused, so a
  legend of that kind yields few exemplars.
* Only point symbols: line swatches, hatches and area patterns are refused, so "wall types" and "materials" are not counted.
* Size band 0.5x to 2x by default; a symbol drawn smaller or larger than that against the legend is missed.
* Room binding needs room polygons in page points. The fact graph rooms of the pipeline were not run on the real sets, so on real
  sets counts are per view, not per room.
* Calibration is on the legend itself (one drawn copy per symbol): it knows turned and recut copies, not the unknown damage of
  real plans, and thresholds are capped by the other symbols of the same legend, so a symbol that is alone in its legend gets
  a looser threshold than one with a similar neighbour.
* The match score ranks detections; it is not a probability and was not calibrated.
