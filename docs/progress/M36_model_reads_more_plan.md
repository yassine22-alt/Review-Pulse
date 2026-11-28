# M36: a larger model that reads more search results (plan, written before any run)

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md). The wording of this plan is kept as it was written before the run.

Written 28 November 2026. No model has judged any candidate when this page is written.

## Why

Of the 9 parts where text bearing on them is written on the drawings but nothing useful is shown, 7 have such text among the
first 50 candidates of the first search stage ([M32](M32_part_by_part_and_vision.md)). Two ideas aim at them.

1. **A reader of candidates.** Qwen2.5-32B-Instruct is asked about each candidate the question the human judging used: opened on
   the sheet, would this piece let a reviewer see what the part asks about, or does it state it? It only picks among text that is
   on the drawings.
2. **Names to look for**, as in M32, with the 32B instead of the 7B, matched exactly in the drawing text.

## Candidates

For each of the 56 parts: the first 20 of the first search stage (words and meaning fused, before reordering), searched four
ways (notes and other written text, each with the part and with the whole line), without duplicates. Made on the laptop
(`scripts/judge_export.py`); the model only reads them on the cluster (`scripts/judge_cluster.py`).

## What is measured

* **Against the judgements already made:** on candidates a person has judged (`benchmarks/austin_stpete_parts_judgements.json`),
  how many of the model's yes answers were judged useful (precision), and how many useful ones it says yes to (recall).
* **In the layout it would have:** per part, the model's yes pieces first (at most 3, in search order), followed by what the app
  shows today. Every new piece it puts there is judged by the same rule by the same person, who sees which pieces came from the
  model; this is not blind, and the page will say so.

## Pass marks, decided now

All three, for the reader of candidates:

| | Mark |
| --- | --- |
| A. Precision of its yes answers on the already judged candidates | at least **60%** |
| B. Parts with a useful piece, in the layout above | at least **30 of 56** (26 today) |
| C. Parts that lose their useful piece | **none** |

For the names: it must add at least **3** parts that neither the app nor the reader of candidates reaches, adding at most 3 pieces
per part on average.

If a mark is missed, the idea stays out of the app and the result is recorded here.

## What this cannot show

The checklist and drawing set are the ones used while building. A pass would be a reason to test it on another set, not proof
that it works there. One person's judgements are the truth used.

## Results (added 28 November, after the run)

Qwen2.5-32B-Instruct answered on one cluster GPU in about 10 minutes (job 6049021). It said yes to 156 of 3013 candidates.
Scored by `scripts/judge_score.py`, written before the answers were read.

| Mark, reader of candidates | Needed | Got | |
| --- | --- | --- | --- |
| A. Precision of its yes answers on already judged candidates | at least 60% | 32 of 43, 74% | met |
| B. Parts with a useful piece in the new layout | at least 30 of 56 | **28** (the app today: 26) | **missed** |
| C. Parts that lose their useful piece | none | none | met, but see below |

| Mark, names | Needed | Got | |
| --- | --- | --- | --- |
| Parts that neither the app nor the reader reaches | at least 3 more | **0** | **missed** |
| Pieces added per part | at most 3 | 2.48 | met |

* **Neither idea goes into the app.**
* **C could not fail.** The layout only puts pieces in front of what the app already shows, so no part can lose one. I did not
  see this when I wrote the mark.
* On the 70 useful candidates judged before, the model said yes to 46%. When it says yes it is mostly right, but it passes over
  more than half of what had been marked useful.
* The two parts gained are 48.1 and 49.2. The layout shows about the same number of pieces (9.05 against 8.64 a part).

**Departures from the plan, and limits.** The judge was an AI assistant, not a person (see the correction at the top). 159 new
pieces needed a mark. Instead of marking them knowing which came from the model, they were shuffled with 40 already marked
pieces whose marks were hidden: 39 of those 40 got the same mark again. That shows the marks repeat, not that they are right.
The two gains rest on new marks, so a stricter grader could lower B. Reaching 30 would need two more parts than this grader
found. The new marks are in `benchmarks/austin_stpete_parts_judgements_m36.json`.

**What I take from it.** A much larger model reading more search results added two parts out of 56. On this set, the way to more
useful evidence is probably not a better reader of the same text candidates. That is an inference from one checklist and one
drawing set, not a proof.
