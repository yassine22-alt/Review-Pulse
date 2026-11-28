# M33: a held out test of the two model vision rule

Written 27 November 2026, **before any of the new drawings were looked at for this test and before any model ran on them.**
The commit that adds this page is the record of that order. Results go in a section added below; the rules above them are not
edited afterwards, and any departure from them is written down as a departure.

## The question

On 87 questions ([M32](M32_part_by_part_and_vision.md)) one combination of two models said yes to nothing that was not there
and, where it said yes, pointed at the thing 30 times of 31. I picked that combination after seeing the results. Does it hold on
drawings that played no part in picking it?

## What is frozen

* **The rule:** a place is shown only when qwen2.5vl:7b, asked about the whole area, says yes **and** Qwen3-VL-32B-Instruct,
  asked on four tiles, says yes. The place is the one the 32B names on its tiles.
* **The code that asks:** `interpreter/vision.py` and `scripts/vision_eval.py` as of commit e248a2e: same prompt, grid,
  tile overlap and picture size. No change before or between runs.
* **The scoring:** `scripts/vision_rule_eval.py` as committed with this page. A place is right when a named cell touches a true
  object and no more than 0.35 of the area is named.

## Drawings and areas

Five sources in `data/real_plans` that no vision question has used: `ch_zeichenhilfe_baugesuch`, `de_baugesuch_cleebronn`,
`de_beispielgrundrisse_3raum`, `nola_sketch`, `rebuildflorida_floorplans`. The files `_chief_1_8` and `_chief_p5` are cut from
the Austin set already used, so they are out.

**Areas, by rule and not by what looks easy:** in each source, going through the pages in order, the first pages that carry a
floor plan, a section or an elevation. One drawing per page, cut to the drawing itself (without title block and note columns),
up to 3 areas per source, and a floor plan among them where the source has one. A page with only words, a site map or a form is
skipped.

## Questions: the same list on every area

So that I cannot choose easy questions, every area is asked all 20:

a door that swings open; a window; a staircase; a toilet; a washbasin or sink; a bathtub; a shower; a kitchen cooktop or range;
a refrigerator; a washing machine; a bed; a table with chairs; a fireplace; an electrical light switch; a smoke detector; a car;
a tree or plant; a written length on a dimension line; a room name written inside a room; a north arrow.

**The key is written by eye from large renders, before any model runs.** For each area and question: there (with a box around
every instance, and whether its name is written beside it: "named" or "drawn"), not there, or **unclear**, when I cannot tell
from the drawing myself. Unclear ones are left out of the scores and their number is reported. The key is committed before the
first run. It is one person's key and no plan reviewer has checked it.

## Pass marks, decided now

All three are needed:

| | Mark |
| --- | --- |
| A. Yes to something that is not there | at most **2%** of the questions about things not there |
| B. Of the rule's yes answers about things that are there, those pointing at it | at least **85%** |
| C. Things there that are drawn only (no name written), found | at least **50%** |

* **If all three are met:** the next test is with areas chosen by the program, not by me. Vision still does not go into the app
  on this result alone, and it would only ever suggest a place to look, never confirm a requirement.
* **If any is missed:** vision stays out of the app, and the page records where it failed.
* Also reported, without a pass mark: each model alone, each source, each question, how many keys were unclear, and the exact
  95% interval of each share, because a few hundred questions cannot show a small rate precisely.

## What this still cannot show

Areas are chosen by hand (by the rule above), so finding the right area is not tested. One object per question is easier than a
line of a checklist. Five sources are few. The two German sources and the Swiss one test another language and drawing habit,
not every discipline.

## The key, written before any run

`benchmarks/vision_held_out.json`. Areas, by the rule: Swiss guide pages 6, 7, 8; German building application pages 2, 3, 4
(page 1 is a site map); German floor plans pages 1, 2, 3; New Orleans sketch pages 1 and 2 (the first floor on page 1); Florida
set pages 3, 4, 5 (the first drawing on each; the cover and the index were skipped). **14 areas, 260 scored questions** (93 about
things there, of which 46 drawn only; 167 about things not there), **20 left out as unclear** (for example circles that may be a
stove, or tables drawn without chairs). "A written length" and "a room name" count as named, so they play no part in mark C.
Before this commit I drew the boxes back on the areas to check them and corrected two door boxes.

## Results (run 27 November 2026, written up 28 November)

**The rule fails. It misses mark C, so vision stays out of the app.** The asking code, the scoring code and the key are the ones
committed before the runs (checked against commit c39a413: no differences). The H100 job took 1172 s including loading the model.

| Mark | Needed | Measured | |
| --- | --- | --- | --- |
| A. Yes to something not there | at most 2% | 1 of 167, 0.6% (95% interval 0.0 to 3.3%) | met |
| B. Of its yes answers on things there, pointing at them | at least 85% | 39 of 45, 86.7% (73 to 95%) | met, narrowly |
| C. Drawn only things found | at least 50% | **14 of 46, 30.4%** (18 to 46%) | **missed** |

Of all 93 things there, the rule found 45. With 167 questions the interval of A reaches above 2%, so even A is not settled.

### Each model alone (no pass mark applies; shown for what it explains)

| | 7B, whole area | 32B, whole area | 32B, tiles |
| --- | --- | --- | --- |
| There: yes (of 93) | 49 | 76 | 81 |
| Drawn only: yes (of 46) | 17 | 35 | 39 |
| Of its yes, pointing at it | 29 of 49 (59%) | 53 of 76 (70%) | 72 of 81 (89%) |
| Not there: yes (of 167) | 3 (1.8%) | 5 (3.0%) | 7 (4.2%) |

### Why it failed

* **The small model hesitates.** Of the 46 drawn only things, the 32B on tiles said yes to 39. The rule kept 14 of them: on 18
  of the others the 7B had answered "unsure", and on 7 "no". The agreement that removed wrong answers also removed most right
  ones.
* **The first 87 questions flattered the small model.** It found 15 of 23 drawn only things there (65%) and 17 of 46 here (37%).
  The 32B on tiles held up much better: 20 of 23 before, 39 of 46 here, and wrong yes answers on 6 of 47 before, 7 of 167 here.
  This is why the test on unused drawings was needed: on the old questions the rule passed all three marks.
* **By source the rule found drawn only things** 0 of 7 (Swiss guide), 7 of 17 (German application), 2 of 9 (German floor
  plans), 0 of 2 (New Orleans sketch) and 5 of 11 (Florida set).
* **Never found by the rule:** beds (0 of 2), tables with chairs (0 of 3), showers (0 of 2), refrigerators (0 of 3) and washing
  machines (0 of 4). Doors were found 2 times in 13.
* **A weakness of the place measure:** 5 of the 6 places counted wrong were "a written length", which stands all around a plan,
  so a true answer names much of the picture and exceeds the 0.35 limit. The measure was fixed beforehand and is not changed.

### The 32B's seven wrong answers, looked at one by one

Done after scoring, without changing the key or any number. Three were north arrows that are not there (where I could see what
it pointed at in two of them, it was a section marker), one a staircase on the posts of a railing, one a bathtub and one a
shower. The seventh, a bed in a German guest room, I may have marked wrongly: a dashed outline in front of the sofa could be a
fold out bed. It should have been "unclear".

### What follows

* **Vision stays out of the app.** This is what the marks said before the run.
* **Not a result, only a lead:** the 32B alone on tiles would meet B (89%) and C (85%) and miss A (4.2% against 2%). I noticed
  this **after** seeing the numbers, so it supports nothing. A use where a wrong suggestion costs a reviewer one look ("check
  here", never "this is shown") might accept another mark than 2%, but that mark has to come from reviewers, and then be tested
  on drawings not used on this page or in M32.
* The 7B on tiles, which the rule does not use, finished later: there, yes for 58 of 93; drawn only, 22 of 46; of its yes
  answers, 46 of 58 pointing at the thing; yes to something not there, 9 of 167 (5.4%).
* Still untested: the program choosing the areas itself.
