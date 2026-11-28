# M35: can a visual search model put the right place first? (plan, written before any run)

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md). The wording of this plan is kept as it was written before the run.

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

## Changes made before the first run (28 November)

No visual search model has been run yet when this section is written.

* **Another model, for its licence.** `vidore/colqwen2.5-v0.2` is listed as Apache 2.0 by the ColPali project, but the model under
  it, Qwen2.5-VL-3B, is under the Qwen **research** licence, as the model's own card says and as the maintainers confirm
  ([issue 334](https://github.com/illuin-tech/colpali/issues/334)). A product could not use it. The model used instead is
  **`vidore/colqwen2-v1.0-hf`**: the same method on Qwen2-VL-2B, which is Apache 2.0. The maintainers describe its quality as
  close; I have not compared the two. This version runs on the `transformers` library alone.
* **A query** is one object on one source file. It is **drawn only** when every place the key gives for it in that source is
  drawn without its name; if any is named, it counts with the named ones.
* **Unclear marks:** for a query, the tiles of an area whose answer the key marks unclear are left out of its pool.
* **The text search** orders the tiles that have text, with the search the app uses (words, meaning, then reordering). Tiles
  without text follow in random order, and its score is the expected value over those orders.
* **Tiles** are pictures with the longer side 1344 pixels, without the grid. The scores come from the model on the cluster; the
  ranking, chance and the text search are computed on the laptop by a script written before the run
  (`scripts/visual_score.py`).

## What this cannot show

Tiles of hand chosen areas are far fewer than the tiles of a whole set, so the score will be higher than in real use. The held
out drawings have been looked at before, for the yes or no test; the search model has never seen them and nothing in its use is
tuned. One person made both keys.

**28 November, after a first attempt that gave no scores:** job 6049029 stopped while loading the model, because the library
`accelerate` is not in the cluster environment. The script now moves the model to the GPU directly. Nothing about what is
measured changed.

## Results (added 28 November, after the run)

`vidore/colqwen2-v1.0-hf` embedded 216 tiles and scored 88 queries in about a minute on one cluster GPU (job 6051290). Scored
by `scripts/visual_score.py`, written before the run. A hit is a right tile among the first 3.

| Queries | How many | Visual search | Chance | Today's text search |
| --- | --- | --- | --- | --- |
| **Held out, drawn only (the ones that count)** | 24 | **96%** (23) | 50% | 62% |
| Held out, named | 28 | 93% | 67% | 75% |
| Older, drawn only | 19 | 74% (14) | 23% | 26% |
| Older, named | 17 | 94% | 14% | 88% |

| Mark, held out drawn only | Needed | Got | |
| --- | --- | --- | --- |
| A. A right tile among the first 3 | at least 70% | 96% | met |
| B. Above chance | at least 25 points | 45 points | met |
| C. Above today's text search | at least 25 points | 34 points | met |

**All three marks are met.** It is the first way of finding things drawn without words that passed a mark set before the run.

**What this does not show.**

* The areas were chosen by hand, and the pools are small: on the held out queries, 3 tiles taken at random already hold a right
  one half of the time. A whole drawing set has many more tiles, so the score there will be lower. By how much is not known.
* It orders places. It does not say that an object is there: asked about something that is absent, it still returns 3 places.
  It must never feed a verdict.
* The keys were made by an AI assistant and nobody has checked them. They were fixed before the model ran.
* On the older drawn only queries it missed 5 of 19, four of them on the large 22 sheet set (a shower, a swinging door, a roof
  slope symbol, a window), where the pools are larger.
* Running it needs a GPU and the `torch` library. It has only been run on the cluster, not inside the app.

**Next, as the plan says:** a test on whole sheets of a drawing set that is in neither key. The app does not change until that
test is passed.
