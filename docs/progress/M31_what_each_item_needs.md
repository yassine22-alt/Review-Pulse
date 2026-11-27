# M31: what each checklist item needs, and where to look

Written 27 November 2026. Measurements on the real St. Petersburg checklist (130 items) against the real Austin permit set (22
sheets). **Both answer keys are mine, made by one person, and no plan reviewer has confirmed them.** The checklist is a Florida
one and the drawings are from Texas, so many items have nothing to find on them. Nothing here is in the app yet.

## What the 130 items need

`benchmarks/stpete_evidence_needs.json`: drawn content 37, filed documents 33, site plan 19, a written fact 17, no requirement
13, two sources agreeing 5, a limit 3, a kind of drawing 3. Only 3 are mainly a limit a formula can check, which is why writing a
rule for each item gets so little from this list.

## Reading the kind with a model (`interpreter/needs.py`, `scripts/needs_eval.py`)

Same instructions for both models, not adjusted after seeing results. If everything were called drawn content, 28.5% would agree.

| | qwen2.5:7b, laptop | Qwen2.5-32B-Instruct, one H100 |
| --- | --- | --- |
| Agreement, three votes | 74 of 130 (57%) | 91 (70%) |
| Agreement, first question only | 64% | 75% |
| A requirement called nothing to check | 1 | 0 |
| A drawing item sent to filed documents | 2 | 8 |
| Time for 130 items | 1114 s | 128 s (plus about 7 minutes to load) |

* Three votes did worse than one question with both models. One ordering on one list does not settle it.
* Skipping the drawings only when both models and all six answers agreed they were not needed would still skip 3 drawing items of
  35 skipped. **So a reading of the kind may only set what is looked at first; it must never stop the drawings being searched.**
* The eight kinds mix two questions, where to look (site plan, other sheets, filed documents) and what to check. Site plan items
  were mostly read as drawn content. A two question design is untested, and needs a checklist not used so far.

## Finding the right sheet (`annotate/evidence_units.py`, `scripts/sheet_search_eval.py`)

The drawing set model (M16) reads sheet and drawing titles in about 9 s and the note search did not use them. I expected that
adding them would help. I graded the sheets for 71 drawing items **before** writing the new search
(`benchmarks/austin_stpete_sheets.json`; 13 more items have no sheet I could name). Several sheets are accepted for many items,
which makes the score lenient: three random sheets would include an accepted one for about 18 of 71.

| What is searched | First sheet right | A right sheet among three |
| --- | --- | --- |
| Notes only (today) | **44** | 62 |
| Notes with their sheet and drawing titles | 43 | 61 |
| Titles only | 28 | 48 |
| Notes with titles, plus titles as pieces | 40 | **64** |

**I do not adopt it.** The full version gains 2 items in the top three (5 gained, 3 lost) and loses 4 at the first sheet. Adding
the titles to the notes alone changed nothing. Without the 18 site plan items the picture is the same (47 to 49 of 53 in the top
three, 33 to 31 first). The example that made me expect a gain, the air handler, did not change: the right sheet was already third
and still is, behind a note about a site survey.

What this says: **by this key, today's search already puts an accepted sheet among three for 62 of 71 items (87%)**. Finding the
sheet is not the main gap. This says nothing about whether the piece shown **answers** the item: for much of the drawn content the
answer is a symbol or a drawing, not a sentence, and this measure does not look at that.

## Next

1. Show the reviewer the sheets to open, from today's search. It is measured above and needs no new model.
2. Measure at the level of the place, not the sheet: a second key saying where on the sheet the evidence is, for the drawn
   content items.
3. Then test a vision model on the drawing frames the drawing set model already cuts (152 on this set), on the H100, against that
   key. The connection to the model server sends text only today; images need new code.
