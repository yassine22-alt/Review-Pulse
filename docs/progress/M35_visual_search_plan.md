# M35: can a visual search model put the right place first? (plan, written before any run)

Written 28 November 2026. No visual search model has been run on these drawings when this page was written. The rules below are
not edited after the first run; any departure is written as one.

## Why

Asking a vision model "is there a toilet here?" failed its test ([M33](M33_vision_held_out.md)): agreement of two models found
too few things, and one model alone said yes to things that are not there. A **visual search** model does not say whether
something is there. It orders pieces of the drawings by how well they match a sentence (late interaction retrieval, the ColPali
family; recent work reports it on civil standard plans, arXiv 2608.26091, on a set and questions unlike ours). Its use would be
"look here first", for things drawn without words.

## What is measured

* **Model:** `vidore/colqwen2.5-v0.2` (listed as Apache 2.0 by the ColPali project), used as published, no training. If it cannot
  be run, the model used instead is named before its first run.
* **Pieces:** every area of the two vision keys (`benchmarks/vision_presence.json`, `benchmarks/vision_held_out.json`) cut into
  3 by 3 tiles with 10% overlap, rendered as `interpreter/vision.py` renders areas.
* **Queries:** each object the keys ask about, in the keys' own words ("a toilet"), once per source file.
* **Pool:** all tiles of that source. A tile is **right** when it overlaps a box the key gives for that object. A query counts only
  if the source has at least one right tile.
* **Score:** is a right tile among the first 3? Reported apart for objects whose name is written beside them and objects that are
  only drawn, which is the case that matters here.
* **Compared with:** (a) chance: the probability that 3 tiles drawn at random hold a right one, for the same queries; (b) the
  text search the app uses today, over the text written inside each tile.

## Pass marks, decided now

On the drawn only queries of the **held out key**, all three:

| | Mark |
| --- | --- |
| A. A right tile among the first 3 | at least **70%** |
| B. Above chance | by at least **25 points** |
| C. Above today's text search | by at least **25 points** |

* **If all are met:** the next test uses tiles of whole sheets of a set not in either key, because here the areas were chosen by
  hand. Only then would the app show places, as "look here first", never as "this is shown".
* **If any is missed:** it stays out of the app, and this page records where it failed.
* The older key is reported but does not count: it was used while building the vision question.

## What this cannot show

Tiles of hand chosen areas are far fewer than the tiles of a whole set, so the score will be higher than in real use. The held
out drawings have been looked at before, for the yes or no test; the search model has never seen them and nothing in its use is
tuned. One person made both keys.
