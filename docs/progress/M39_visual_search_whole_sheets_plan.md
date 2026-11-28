# M39: visual search on whole drawing sets (plan, written before any run)

Written 28 November 2026. **When this page is written, no page of the two new sets has been rendered or looked at, no key
exists and no model has run on them.** I have seen the page count, sizes and word counts of both files, and the search result
that led to the first one showed its sheet list. The rules below are not edited after the first run; any departure is written
as one.

## Why

The visual search model passed all three marks of [M35](M35_visual_search_plan.md), but on small pools of areas chosen by hand.
A reviewer has whole sets. This test asks the same thing of every page of two sets that are in neither earlier key.

## The sets, and how they were chosen

The first two results of one web search for sample residential permit drawing sets that are multi page residential sets and
not from a source already used (a second result from the maker of an earlier test set was left out for that reason). Both are
public. Neither is stored in the repository.

| Set | Pages | Selectable words | SHA-256 starts |
| --- | --- | --- | --- |
| A permit set published by San Jose / Santa Clara County planning | 25 | some | `9354e18663472203` |
| A sample set for a home addition published by the city of Lynnwood | 9 | none | `6f51f94ddbdc0023` |

## What is measured

* **Model:** `vidore/colqwen2-v1.0-hf`, used as published, as in M35.
* **Tiles:** every page of both sets cut into 4 by 4 tiles with 10% overlap, nothing chosen or left out. Each tile is rendered
  as a picture with the longer side 1344 pixels.
* **Queries:** the object phrases of the two earlier keys, in their words, once per set. A query counts only if the set has at
  least one right tile.
* **Pool:** all tiles of that set. A tile is **right** when it overlaps a box the key gives for that object. A tile where the
  key says it cannot be told is left out of that query's pool.
* **Drawn only:** every place the key gives for the object in that set is drawn without its name. If any is named, the query
  counts with the named ones.
* **Score:** is a right tile among the first 3? The first 5 and first 10 are reported, and decide nothing.
* **Compared with:** chance for the same queries, and the app's text search over the words inside each tile, scored as in M35.
  For the set without selectable words, the app's text reader (OCR) reads each tile, as the app would for a page without words.

## The key

An AI assistant writes it from large renders of the pages, **before the model runs**, and it is committed before the run. No
person checks it. A place the key misses counts against whichever search returns it, so missed places make all three scores
look worse. The grader has seen the M35 result.

## Pass marks, decided now

On the **drawn only** queries of both sets together, all three:

| | Mark |
| --- | --- |
| A. A right tile among the first 3 | at least **50%** |
| B. Above chance | by at least **25 points** |
| C. Above today's text search | by at least **25 points** |

If there are fewer than **10** drawn only queries, the result is **inconclusive**, whatever the scores.

A is lower than in M35 (70%) because the pools are many times larger. I choose 50% as the point where looking at three
suggested places still saves a reviewer searching a set by hand half of the time. That is my judgement, not a tested need.

* **If all are met:** the visual search is worth building into the app as an optional "look here first" list, which never
  says that something is there and never feeds a verdict. It needs a GPU and `torch`.
* **If any is missed:** it stays out of the app, and this page records where it failed.

## What this cannot show

Two sets from two places are not "any drawing set". Both are residential and in English. A pass does not show that reviewers
find the suggestions useful.
