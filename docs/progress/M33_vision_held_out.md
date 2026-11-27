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
