# M32: each requirement part by part, and what a vision model can and cannot see

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md).

Written 27 November 2026. This follows [M31](M31_what_each_item_needs.md). **All answer keys here were made by an AI assistant, and
nobody has checked any of them.** The checklist is a Florida one and the real drawings are from Texas, so many lines
have nothing to find. Nothing here is "working" in the sense of [REVIEWER_WORKFLOW.md](../REVIEWER_WORKFLOW.md); it is built.

## In the app now

For each requirement the review desk shows:

* **the parts it asks for**, each copied word for word from the requirement. A model only says where to cut; code drops any part
  that is not the requirement's own words, and a line stands whole when nothing survives (`interpreter/parts.py`);
* **where to look**: the notes closest to each part, and the labels, table rows and measurement counts written on the drawings,
  each with its sheet and a button that shows it (`annotate/evidence_units.py`);
* **the five closest notes for the whole line**, always;
* **two ticks per part**, "I saw it on the plans" and "It is missing". A missing part blocks "Shown on the plans", and starts the
  correction comment from the requirement's own words, which the reviewer edits. Ticks are kept with the decision, and a tick is
  accepted only for a part the reviewer was shown.

Only the checklist's words go to the reading model. Pictures of drawings are refused for any model outside this machine and its
private network (`llm/openai_compat.py`), which matches what the hosted model consent covers.

## Finding evidence, part by part (measured)

The 37 lines of the St. Petersburg checklist that ask for something drawn were cut into 56 parts (the model cut 11 lines; the
others stand whole). The results of today's search and of the new one were mixed and shuffled, and each piece was judged by an AI grader on one
rule: opened on the sheet, would it show what the part asks for, or state it? The wording of a label can hint which search
found it, so the judging is not fully blind (`scripts/parts_eval.py`, `benchmarks/austin_stpete_parts_judgements.json`).

| What the reviewer is shown | Parts with at least one useful piece | Pieces to read, 37 lines |
| --- | --- | --- |
| Today: 5 notes for the whole line | 23 of 56 | 185 |
| First design: 2 notes and 3 drawing texts per part | 20 of 56 | 270 |
| 5 notes, plus 2 notes per part | 25 of 56 | 221 |
| **Adopted: 5 notes, plus 2 notes and 3 drawing texts per part** | **27 of 56** | 384 |
| Drawing texts alone | 13 of 56 | 163 |

* **My first design was worse than what it replaced** (7 parts lost, 4 gained): two notes per part dropped notes that stood third
  to fifth for the whole line. The adopted layout keeps those five, so by this judging it loses nothing.
* **What it costs:** about twice the pieces to read if every one is opened. The screen shows one or two per part and folds the
  rest, which I have not measured with a person.
* **The layout was chosen after seeing these results.** It needs a checklist and a drawing set not used here before the gain
  can be claimed.
* These rows were measured with the reordering model scoring in batches. It now scores one pair at a time (below), and this
  layout gives **26** of 56 against 23 for today's.
* The gain is small: **3 to 4 parts**. The larger value I expect is the part list, the ticks and the drafted comment, and only a
  reviewer can confirm that.

## Why 29 parts have nothing from either search

I searched every text on the set for each of them.

| Cause | Parts | Examples | What would help |
| --- | --- | --- | --- |
| I found nothing on this set that supports them: probably absent or not applicable | 19 | Flood zone and vents, masonry, signed and sealed drawings, attic access, gable bracing, revision clouds | Nothing to find. A reviewer ticks "missing" or "does not apply". A matching checklist and set would test more |
| **Text about them is on the set and both searches missed it** | 9 | "HEAT/AC PUMP" for "air handler"; "WATER HEATER" for "appliances"; room names for "all rooms"; a "1 : 12" mark for "roof slopes"; "TYPE X" for "fire resistant materials" | See the next section |
| Only a drawing answers it | 1 | A section through a typical window on both floors | Vision, or the reviewer |

The split between "absent" and "missed" is my own reading of the set.

### Tried and not adopted: looking for the names a drawing would write

A requirement names a kind of thing and a drawing names the thing. The reading model was asked, once and without tuning, for names
a drawing might write for each part, and those words were matched exactly (`scripts/expand_eval.py`). It reached **2 more parts**
(the rooms, and the exhaust fan legend) for up to 6 more pieces per part, about 3 s per part. When it proposed real names
("toilet", "sink") they worked; for "appliances" it gave back the requirement's own words. **Too little for the extra reading, so
it is not in the app.** A stronger model may propose better names; that is untested.

## Vision: can a model confirm what is drawn?

`benchmarks/vision_presence.json`: 87 yes or no questions on 10 areas that I chose by hand from two sets (the Austin set and a
one sheet Millcreek sample). 40 things are there, 47 are not, many of them plausible (no smoke detector on a sample whose own
list asks for one). The key was written before any model ran. The model answers yes, no or unsure and names cells of a grid
laid on the picture; a yes without a cell counts as unsure. A place counts when a named cell touches the object and no more than
about a third of the picture is named (a random single cell would touch it about 1 time in 5).

qwen2.5vl:7b on the 6 GB laptop (about 1 s a question, 4 to 6 s with tiles):

| | Whole area | Four overlapping tiles |
| --- | --- | --- |
| Named on the drawing ("WATER HEATER"): yes | 16 of 17 | 16 of 17 |
| Drawn only (toilet, stairs, door swing): yes | 15 of 23 | 17 of 23 |
| Yes **and** pointing at it | 22 of 40 | 27 of 40 |
| **Yes to something that is not there** | **0 of 47** | **3 of 47** |
| Unsure about something that is not there | 11 of 47 | 32 of 47 |

* **What fails:** small abstract symbols. Light switches and door swings were missed by both ways of asking.
* **False yes:** all three were "a staircase", on tiles, on groups of parallel lines. Cutting into tiles removes the context that
  says they are not stairs.
* **Places:** on the whole area the named cells were often wrong although the yes was right (some looked off by a row). Tiles
  placed named objects better (15 of 16 against 11 of 16).
* **What this does not show:** the areas were chosen by hand, so no search is tested; one object per question is easier than a
  checklist line such as "all receptacles that need protection"; two sets and 87 questions are small; a zero on 47 does not mean
  a rate of zero. **Nothing from vision is in the app.** If it is added, it may only suggest places to look, never confirm.

### The same questions with a larger model on one H100

Qwen3-VL-32B-Instruct (Apache 2.0), served by vLLM on one H100, same questions, same grid, same code. The whole job took 786 s
including loading the model.

| | 7B whole | 7B tiles | 32B whole | 32B tiles |
| --- | --- | --- | --- | --- |
| There: yes (of 40) | 31 | 33 | 37 | 37 |
| Named on the drawing (of 17) | 16 | 16 | 17 | 17 |
| Drawn only (of 23) | 15 | 17 | 20 | 20 |
| Yes and pointing at it | 22 | 27 | 34 | **35** |
| Not there: yes (of 47) | **0** | 3 | 2 | 6 |

* **The larger model finds more and points far better.** So many of the small model's misses and wrong places were the model's
  limit, not the task's.
* **It is more sure and not safer.** On tiles it said yes to 6 things that are not there. It never answered "unsure" on tiles (43 yes, 44 no).
* **Its mistakes look like guesses from drawings it has seen:** a smoke detector on both Millcreek areas, which show none (that
  sheet draws lights as small circles); a bathtub twice on the Austin set; a ceiling fan; a staircase on parallel lines. None of
  these areas came with the sheet's legend, and giving the model the legend is untried.
* Two things were missed by all four ways of asking: a light switch and a door swing in the bedroom area.

**Two models that must agree.** Combinations of the four runs, a yes only when both say yes:

| Rule | There: yes (of 40) | Yes and pointing at it | Not there: yes (of 47) |
| --- | --- | --- | --- |
| 7B whole and 32B tiles (place from the 32B) | 31 | **30** | **0** |
| 7B whole and 32B whole | 31 | 28 | 0 |
| 7B tiles and 32B tiles | 33 | 31 | 1 |
| 32B whole and 32B tiles | 36 | 34 | 2 |
| 7B whole and 7B tiles | 30 | 26 | 0 |

The first rule keeps what the small model found, no more, loses 6 things the 32B alone would have found, and where it says yes
it points at the thing 30 times of 31. **I picked it after looking at these numbers, among the combinations I tried, so these
87 questions cannot show that it works.** Its zero is on 47 questions, which does not mean a rate of zero. What would show it:
the rule frozen as written here, and new areas from drawing sets not used above, with the key written before any model runs.
It also needs a card that holds the 32B model, which an office's own computer may not have.

## What a reviewer waits for, and two faults found while measuring it

The first version of this screen made a reviewer wait: about 90 s for the first item and 6 to 29 s for a later one. Timing every
step showed two faults that were older than this screen.

1. **Every call to the local model server waited about 2 s for nothing.** The app addressed it as "localhost". Windows tries the
   IPv6 address first and the server listens on the IPv4 one: 2.10 s a call by name, 0.05 s by address, for work the server did
   in 0.05 s. Every part of the app that asks a local model paid this: reading, search and sheet recognition. The name is now
   replaced by the address in one place (`llm/local.py`). Any timing of local model work measured before this on Windows
   includes it.
2. **The order of search results depended on which texts were scored together.** The reordering model is stored in whole numbers
   with a scale worked out from the whole batch. On 32 real reorderings, the same texts in another order changed which five came
   first in 18. Scored one at a time, the order of the texts changed nothing (32 of 32, scores identical), and it was faster
   (18.7 s against 32.3 s in that run) because short texts are no longer padded to the longest. Grouping texts by length was also
   tried: faster, but it changed the first five in 20 of 32, so it was not used.

Effect of scoring one at a time on the same judged parts (72 new pieces judged by the same rule):

| | Batches of 8 (before) | One at a time (now) |
| --- | --- | --- |
| Today's layout: parts with a useful piece | 23 of 56 | 23 of 56, the same parts |
| This screen: parts with a useful piece | 27 of 56 | **26 of 56** |
| Items whose five notes are the same set under both | 17 of 37 | |

**I adopt it and record the loss:** one part ("room dimensions") no longer shows the room label with its area. In return the same
search gives the same pieces every time, which a review record needs.

First openings of the 37 items took 824 s in all before the two fixes and 256 s after (about 7 s each, including loading).

**Searching ahead.** After the drawings and the requirement document are uploaded, the server now searches every requirement in
the background (`app/prepare.py`), stops while a person is waiting for a search of their own, starts over when the drawings or the
document change, and does not run with a hosted reading model. The desk shows how many are ready. A prepared item opens in
0.01 s. Preparing all 130 lines of the real checklist took **575 s** (about 10 minutes, the first 10 of them 83 s with the models
loading), after which opening 20 prepared lines took 0.42 s together.

A fault this would have made worse is fixed too: a search still running while new drawings were analysed could have been saved as
the result for the new drawings. Saved results are now named after the exact analysis they were read from.

**A race older than these changes, found by the browser walkthrough.** The desk and the submission page asked for the job list
beside the data. A job that ended between the two answers left old data on screen with no job running to ask again: a correction
in the list with no pin on the drawing. The walkthrough failed 4 times in 10 runs this way (2 of 6 with searching ahead switched
off). Both screens now ask for the jobs first; 10 of 10 runs passed.

## Tried: finding legend symbols by their exact strokes

The vision model missed small symbols, and this set is a vector PDF with an electrical legend, so I tried finding each legend
symbol's exact strokes on the sheet (59,450 strokes; quarter turns and mirrors). **It does not work here:** none of the five
switch shapes was found although the plan shows many switches. In this file a legend symbol is hundreds of strokes 0.2 to 0.5
points long; on the plan the same symbol is drawn smaller and cut into different strokes, and the file has no reusable symbol
objects. A few very small shapes matched dozens of times and appear to be pieces of other things.

Two picture based ways were then tried on one area, with templates cut from the legend automatically (sizes, quarter turns,
mirrors). I estimate by eye about 35 switch signs in it; this is a rough count, not a graded key.

| Way | Switch signs found | Wrong places |
| --- | --- | --- |
| Exact strokes | 0 | |
| Picture correlation, score at least 0.6 (a threshold read off this same area) | about 8 | 3 |
| Shape only (both thinned to one pixel, distance between lines both ways) | not counted | at least 164: 199 places at the strictest distance listed |

The legend sign is drawn with thin lines for its size and the plan signs are small and bold, which I think is why correlation
scores are low; thinning removes that difference and with it most of what tells the sign from other lines. **None of this is
in the app, and I stop here rather than tune to one drawing.** The untried option is a model trained to spot symbols on
drawings, which has to be shown to carry over to sets it was not trained on.

## Could a model that reads more results reach what is missed? (28 November)

For the 9 parts where text bearing on them is written on the drawings but nothing useful was shown, I looked up where the first
such text ranks in the first search stage, before reordering (`scripts/depth_eval.py`; notes and other written text searched
apart, with the part and with the whole line). What counts as bearing on a part is a word pattern I wrote, so **a match is a
candidate to be judged, not a useful piece**.

| Among the first | 5 | 10 | 20 | 50 |
| --- | --- | --- | --- | --- |
| Parts with such text in at least one of the four searches (of 9) | 5 | 5 | 6 | 7 |

So a model that reads 20 to 50 candidates and picks the useful ones could reach **at most 7** of these 9, if every match turned
out useful; that is the ceiling on what it can add to the 26 of 56. The ceiling needs all four searches, so such a model would
read the candidates of each. Two are out of reach this way (chimneys, and the fire resistant board note, which ranks 58th).
Five rank among the first 5 before reordering and still did not become a useful result; I have not checked for each whether the
reordering moved it away or the match is not useful.

## Known limits

* Door and window size marks such as "2668" are read as measurements.
* A table inside a drawing frame that is too large is read as rows that mix in text beside it.
* Most lines (26 of 37) were not cut: a line with several things in one phrase stays whole.
* The ticks and the part list have not been used by a reviewer.
* Both the checklist and the drawing set used for these numbers were also used while building. A held out pair is the next
  measurement that matters.
