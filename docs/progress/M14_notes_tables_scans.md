# M14: what the drawings say, tables that can be reached, scans that keep their lines

This note is for someone who has not followed the project. M13 ended with one finding: reading a requirement document is solid, and
facts are now the bottleneck. Most lines of a real plan-review checklist ask about things a plan view does not draw to measure
(smoke alarms, fire ratings, handrails). This milestone starts on that, and repairs three weaknesses of the reading step that M13
had listed as open. For each one I first looked at what the 2026 literature does, then measured with the label-free tools, and I
record what was lost as well as what was gained. Every number below can be reproduced with the commands at the end.

## What I looked for in the literature, and what I took from it

| Question | What I found | What I did with it |
| --- | --- | --- |
| How do current systems get the facts a plan view does not draw (alarms, ratings, handrails)? | Learned symbol spotting on vector drawings (SymPoint, CADSpotting, and two 2026 papers that add the drawing's text as a third input) and raster detectors (a 2026 pipeline uses YOLOv8 on 18 symbol classes). All need labelled drawings and a GPU. A 2026 study of automated plan review on real permit sets reports that looking a note up in the text layer of a vector PDF works (note lookup 2 of 2, note text 2 of 2) while recognising symbols does not (0 of 2), and a 2026 benchmark (AEC-Bench) reports that finding the right sheet is the hard part. | I did not train a symbol detector: I have no labelled symbols and the evidence says the text is the reliable signal. I read what the sheets say in words, over every sheet of the submission. |
| Is it safe to measure with defects planted in generated drawings? | The same plan review study shows how this goes wrong: planted defects have side effects the answer key does not name, and their "clean" cases were not clean. | The generated notes block is used only to check that a mention is found and that a missing mention is caught. I do not claim anything about real drawing sets from it. |
| How should a table that the text refers to be found? | Document parsers (Docling with TableFormer, MinerU) recognise table structure with trained models; structure-aware retrieval for legal text resolves references before use. | The tables of our real documents turned out to be ordinary vector tables that were read but never named, so the reference had nothing to point at. Naming a table by its caption needs no model. A trained structure model would only help the four tables drawn without vertical rules; I read those from the gaps between words instead and record the limit below. |
| Which OCR keeps accents? | PaddleOCR publishes one recogniser for Latin-script languages (PP-OCRv5, 8 MB, Apache 2.0). Docling's documentation notes that engines differ in which languages they are validated on. | I use that recogniser through the engine we already have, chosen by the script the page shows and never by a language setting. |

## What was wrong, and what I did

| Defect found | Effect | Fix |
| --- | --- | --- |
| The plan model had no fact for anything a sheet only states in words | Every line about alarms, fire ratings, handrails, safety glazing was declined | The text of every sheet of a submission is searched for nine kinds of note, and each becomes a counted fact of the building ("how many times the set mentions smoke alarms"). The kinds are a data file (`annotate/lexicon/notes.yaml`): a new kind, in any language or discipline, is one entry and no code |
| General notes sit on their own sheet, not on the floor plan | A floor plan alone would say "never mentioned" about a set that mentions it four times (seen on a real permit set, where the notes are on sheets 13, 18 and 19) | The count is over all sheets. A count of zero is trusted only when the text of every sheet was read |
| The door schedule's fire rating column was not read | "20 MIN", "1 HR", "EI30" were ignored | Each door carries its rating in minutes when the schedule gives one |
| The local model never used the new facts on its own (0 of 46 lines) | The facts existed but no rule used them | A last arm, built by a program and not by a model: when every other arm has declined a sentence and the sentence names a kind of note, the rule "the drawing set mentions it" is written. When the whole set never mentions the thing, a warning asks a person to look; it is never a failure. It never passes on its own: where the thing is and whether it is right are listed as not checked. A sentence that negates or excuses ("not required", "unless", "except") is left declined |
| A table in a PDF was named after its page ("table p139.1") | "See Table B4" could never reach it. By the count of the new tool, 0 of 168 table references in the UK volume and 0 of 28 in the US standard reached a table | A table takes the name of the caption it sits under. A table that goes on over the page stays one table, and the header printed again on the next page is not a row |
| "Table B4", "Tables C1 and C2" were not recognised as references | Annex tables and plurals were skipped | The reference pattern reads a letter before the number and the plural |
| Four tables of the UK volume have horizontal rules only | The table finder returned nothing for them | Under a caption with no ruled table, rows are read from the gaps between words, and a wrapped line is joined to the row above it |
| Table detection stopped after 150 seconds | On a busy machine the UK volume was cut at page 153, so two people could see different clauses. I saw this happen during this work | The limit is a number of pages (600 with ruling lines), the same on every machine |
| The cache of a split document was not renewed after the splitter changed | The app would have served the old split. I caused this myself during this work and the audit caught it | The splitter version is raised, and the note in the code says when to raise it |
| OCR decided for every line whether it was upside down | On long lines of small print it was often wrong: the line was turned, read as noise and dropped. On one clean French page 8 of 36 lines were lost. This, not the accents, was the main cause of the low recall on scans | A page has one orientation: it is read as upright first, and the per-line decision is only a second try when the upright reading is poor |
| The default recogniser drops accents ("etre" for "être") | French and German words came out wrong | The Latin-script recogniser reads the page again when the first reading is in Latin script. Its own confidence cannot choose: on a Chinese page it returns the digits alone and is sure of them |

## Results

Reading, measured without labels:

| | M13 | M14 |
| --- | --- | --- |
| Format robustness, 32 variants of four checklists: recall and precision | 0.956 and 0.980 | 0.987 and 0.993 |
| Scan variants alone (recall) | 0.57 (French) to 0.84 | 1.00 on all four |
| References that resolve, splitter audit on nine documents | 82 of 119 | 119 of 119 |
| References to a table that reach the table, UK volume (`scripts/table_refs.py`) | 0 of 168 | 165 of 168 |
| The same, US standard | 0 of 28 | 28 of 28 |
| Obligation sentences inside one clause | 3 461 | 3 461 |
| Obligation sentences cut in two, in running text | 8 | 8 |
| "Sentences" that run over several table rows | 15 | 29 |
| Clauses starting in the middle of a sentence | 20 | 20 |
| Table rows read: US standard, UK volume | 79, 449 | 288, 729 |

The three table references of the UK volume that do not resolve, and the one of the St. Petersburg checklist, point to tables of other
documents (Volume 2, a British Standard, the building code). Left unresolved is the right answer for them.

The audit used to give one figure for cut sentences (23 in M13). It rose to 37, so I looked at where. Rows of a table have no full
stop, and the audit reads several rows as one long sentence. All of the rise is there, because many more rows are read. The audit
now reports running text and tables apart.

Checklist benchmark, local model qwen2.5:7b, all 291 lines of the four checklists, on a generated plan that carries a block of
general notes (the wording of the notes is mine, in the style of permit drawings):

| | M13 full run | M14 |
| --- | --- | --- |
| Lines a plan can decide with measured facts | 10 | 10 |
| Of those, turned into a correct rule | 8 | 8 |
| Wrong rules on those lines | 0 | 0 |
| Rules on measured facts written where none was expected | 4 | 3 |
| Lines that were declined and now carry a mention rule | 0 | 20 |
| Lines with the same outcome as in M13 | | 268 of 291 |

I compared the two runs line by line. 23 lines changed: 20 declined lines now carry a mention rule, two invented rules of M13 are
gone (they were removed by the fixes at the end of M13), and one declined line became a rule: "Stairways must be min. 3' wide" is
now "every room of type stairs is at least 0.9144 m wide". It has the right number and says what the sentence says, but my label
for that line expects no rule (the generated plan has no stair), so it counts among the three rules written where none was expected.
The other two are the half faithful "the drawing is dimensioned" readings M13 already describes.

I read the 20 mention rules one by one. In all 20 the thing the rule looks for is what the line is about (fire rating for "must be
1-hr rated", smoke and carbon monoxide alarms for "location of smoke detectors and carbon monoxide detectors"). 17 are on lines I
had labelled "about the plan, but the plan lacks the fact", two on lines I had labelled "not about a floor plan" (fire rated
exterior walls near a lot line, 1-hour rated projections), one on a line that holds several requirements. The labels were written
before this arm existed and I did not change them.

Reading them showed a problem I had not planned for: about 9 of the 20 sentences apply only in some cases ("townhouses require an
automatic sprinkler system", "handrails on stairs with 4 or more risers", "if applicable"). A rule that failed whenever the set
does not mention the thing would raise a failure on a house that needs no sprinkler. So a mention rule is advisory: when the set
never mentions the thing, the finding is a warning that asks a person to check whether the requirement applies. It is never a
failure, and the coverage report lists the clause as not decided, with that reason.

The local model, given the new facts but not the new arm, used none of them (0 of 46 lines) and changed nothing else on the 56
labelled lines I ran that way (8 of 10 correct, 0 wrong). So the facts did not disturb the rules it already wrote.

## Losses I accepted

* A mention is not a measurement. "The set mentions smoke alarms" says nothing about where they are. The rule says so in its own
  words and can never report "satisfied".
* The nine kinds of note are a list somebody wrote. A thing that is not in the list is not found. The stronger design is to look
  for whatever the sentence names (retrieve the passages of the sheets with a multilingual embedding model, then let the model
  choose among them in both orders, which is the kind of question our small model answers reliably). I have not built it.
* A conditional sentence ("a handrail on stairs with four or more risers") becomes a mention rule too, and nothing here knows
  whether the condition holds. This is why a miss is a warning and never a failure. It also means a mention rule never produces a
  verdict: it points a person at the right place, no more.
* Three rules on measured facts are written where my labels expect none (M13 reported one after its last fixes, checked on single
  lines and not on a full run; its last full run had four). One of the three is faithful and two are half faithful.
* Notes drawn as outlines are not counted on a vector sheet (no OCR is run for notes there), and then a zero is not trusted.
* A table without vertical rules is read from white space: the words are all there, but which cell a word belongs to is a guess
  when cells are close.
* A caption is recognised by its shape (the table's name, then a title that starts with a capital and does not end with a full
  stop). A caption written as a sentence is missed and its table keeps a page name.
* Scans cost more time: a page in Latin script is recognised twice (once per recogniser).
* A page scanned sideways is still not handled. Upside down is.

## Still open

* A real second plan. One real permit set was only used to see where its notes are; nothing was scored on it.
* A hosted model has still not been run on this code, and the labels are still by one person.
* Drawn symbols with no word beside them (an alarm symbol with no legend) are not found.

## Reproduce

```powershell
python -c "from reviewpulse.rules.readers import fetch_latin_model; print(fetch_latin_model())"   # once: the Latin-script OCR model
python scripts\format_robustness.py
$env:SPLIT_CACHE = "reports\split_cache_m14"; python scripts\split_audit.py data\real_docs --json reports\split_audit.json
python scripts\table_refs.py data\real_docs --json reports\table_refs.json
python scripts\checklist_benchmark.py --out reports\benchmark --plan-notes
```

`REVIEWPULSE_NOTES=0` leaves the note facts out and `REVIEWPULSE_MENTIONS=off` switches the last arm off, to measure what each
changes. `REVIEWPULSE_OCR_LATIN` names another place for the OCR model file.
