# M32: each requirement part by part, and what a vision model can and cannot see

Written 27 November 2026. This follows [M31](M31_what_each_item_needs.md). **All answer keys here are mine, made by one person, and
no plan reviewer has confirmed any of them.** The checklist is a Florida one and the real drawings are from Texas, so many lines
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
others stand whole). The results of today's search and of the new one were mixed and shuffled, and each piece was judged by one
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
* The gain is small: **4 parts**. The larger value I expect is the part list, the ticks and the drafted comment, and only a
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

A larger model (Qwen3-VL-32B-Instruct, Apache 2.0) is to be measured with the same questions on one H100, to tell the limits of
the small model from the limits of the task. **Not yet run when this was written.**

## What a reviewer waits for

On the 22 sheet set on the 6 GB laptop, with the splitting model local (six lines, a fresh copy of the project):

| | Wait |
| --- | --- |
| The first item of a session (models load) | about 90 s |
| A later item opened for the first time | 6 to 29 s, longer with more parts (1 to 6 parts) |
| An item already prepared | 0.01 s |

The desk prepares the next undecided item while the reviewer reads the current one, and results are kept until the drawings are
read again. **A reviewer who jumps elsewhere in the list still waits, and 90 s for the first item is too long for real use.**
Preparing every line right after upload is the next step if reviewers confirm the part list is useful.

## Known limits

* Door and window size marks such as "2668" are read as measurements.
* A table inside a drawing frame that is too large is read as rows that mix in text beside it.
* Most lines (26 of 37) were not cut: a line with several things in one phrase stays whole.
* The ticks and the part list have not been used by a reviewer.
* Both the checklist and the drawing set used for these numbers were also used while building. A held out pair is the next
  measurement that matters.
