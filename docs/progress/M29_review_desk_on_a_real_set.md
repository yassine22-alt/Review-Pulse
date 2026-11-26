# M29: the review desk on a real permit set

Written 26 November 2026. Until now the app had only been walked through on a generated one sheet plan. This is the first run on
`chief_architect_austin.pdf` (22 sheets) with the St. Petersburg residential checklist (130 requirements) and the local model
qwen2.5:7b, on one laptop with a 6 GB graphics card. Evidence search over the drawing notes was switched off for speed, so this
run says nothing about it.

## Reading the files

| Step | Result |
| --- | --- |
| Drawings | 569 s (9.5 minutes); 38 rooms and 3585 elements reported. I did not check them against the drawings |
| Checklist upload | 1103 s (18 minutes), most of it drafting rules the review desk never shows. Fixed, see below. Not re-timed |

## The model on real checklist items

The checklist states few limits that can be measured on a drawing; many items ask for something to be shown. I took the 14
items 51 to 64 of its Building Plans section, chosen by section before seeing any result, and read each output against its item.

| Result | Items |
| --- | --- |
| A measured check | **0** |
| A check that only asks whether the drawings mention something, and says so | 2 (stairs: handrails and guards; smoke and CO detectors) |
| Declined | 12 |

Item 52 ("29 inch minimum clear access") is the one plain numeric limit. The checks rightly refused a rule that used a number the
sentence does not state (1.75), and no correct rule was written: **a miss**. Approving one of the two mention checks was then
refused by the server ("unsupported source quote/span: item 55"), so a check that was offered for approval could not be
approved. Not fixed. For two other items the model produced a long meaningless expression; they stayed unapproved.
It took 32 to 132 seconds an item.

## The desk with many findings

To fill the desk I also ran the built in rule pack. The product app does not offer packs; this was to test the screens. The check
gave 223 warnings, 91 not evaluated, 8 passes and 1 failure, shown as 24 correction items.

Fixed after this run (tests in `tests/unit/test_real_set_fixes.py` and `tests/app/test_accounts.py`):

| What the real set showed | Cause | Fix and result |
| --- | --- | --- |
| The correction list took 9.5 s to build, again on every request and several times per decision | 22 sheet files were loaded from disk each time (99% of the time) | Kept in memory until a file changes. Once loaded: 0.2 s. Marked up PDF export 28 s to 0.8 s, CSV 30 s to 0.4 s. A keyboard accept now answers in about 1.0 s (three timed; not timed before) |
| `{room.label} is reached only through {witness.blocking}` shown as a finding | A sentence that words a violation was used where no violation was found, and filling it failed | Such a finding now says what was read and what is required |
| Sheets listed as 1, 2, 11, 12 | Files sorted by name | Page order |
| "Show on the drawing" with nothing to show | A finding with no shape counted as a place | Only shapes that can be drawn count |
| 18 minute checklist upload | The older per clause drafting ran at upload | The app with accounts only splits the document; a requirement is read when asked. The older pages are unchanged |

The first opening of the desk on this set still takes about 15 s.

## Fixed in a second pass

**A shortfall on one sheet read as a violation.** "At least one exit door: detected 0" was found on one sheet of the set. The
older rule path judged a rule about the whole dwelling from one sheet. What changed (`engine/setwide.py`, with the rules that
depend on the whole building declared in `rules/registry.py`):

* a count with a minimum is read across the set: if one sheet reaches it, it is met (sheets are not added up, since two may draw
  the same door); otherwise there is one undecided result naming the sheets read;
* a route that was not found is undecided on a sheet a route can leave: one with no exit to the outside, or with a stair, a
  stair room or an UP or DN mark. A sheet with its own exit and no way to another level keeps its violation. My first version
  made every route in a multi sheet set undecided, and the existing two plan test caught that it lost a planted violation;
* a maximum that is exceeded, and findings about one element, are unchanged.

On the real set: 0 items "revision required" (before: 1, the false one). **Limit:** a partial sheet that shows its own exit and
no stair or level mark is still judged alone. Stairs the reader misses and are not marked in words have the same effect.

**An engine sentence shown as a quote.** Only rules whose source is the uploaded document are matched to its clauses and quoted.
Others are headed "A built-in rule, not from your document", cited as built in, and never take a clause number of the upload. An
item now lists the findings behind it, which is also what places its pins.

**A check that could not be approved.** The second reader (the model) raised a concern and quoted words that are not in the
clause as given; the app then threw away the whole second reading. Quotes are now located by their words, since a model cannot
count character positions. A concern whose quote is nowhere is kept, tied to the whole clause, and says so. The refused check
now approves. The second reader's concerns on it were repetitive and of little use: that is not fixed.

## Still open

1. **A number that should not be shown.** "BEDROOM 3 measures 247 m2" on a sheet whose title block says no scale. The item says
   the scale is unverified, but the figure is plainly wrong and should not be printed.
2. **Rooms that are not rooms.** A block of kitchen and cabinet notes was read as a room with no way out.
3. **Internal words** still reach comments: "room_graph", "path to EXIT", unnamed rooms as "room 8469".
4. **A second reader that adds noise.**
5. **Speed.** About 10 minutes for the drawings, and about a minute for each requirement the model reads.

## What this means

The screens hold up on a 22 sheet set after the fixes. What the product can decide on a real checklist does not: none of the 14
real items became a measured check. Demonstrate the desk, and do not claim that it reviews a real checklist.
