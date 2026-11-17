# M13: reading whatever document the user brings

This note is for someone who has not followed the project. After M12 I asked whether I trusted the first step of the pipeline, the
one that turns a requirement document into clauses. I did not have a measure for it, so I built three, found real defects with them,
fixed what they showed, and measured again. Every number below can be reproduced with the commands at the end.

## What I measured, and why

| Measure | What it asks | Script |
| --- | --- | --- |
| Splitter audit | On nine real documents (4 checklists, a 280 page US standard, a UK fire safety volume, 3 French texts), does an independent reading of the text agree with the clauses? It counts obligation sentences that lie inside one clause, sentences cut by a clause boundary, and clauses that start in the middle of a sentence. No label is needed. | `scripts/split_audit.py` |
| Format robustness | If the same checklist arrives as plain text, a numbered list, Word, two kinds of Excel sheet, csv, a web page or a scan, are the same clauses found? The clauses of the original are written out in each format and read back. | `scripts/format_robustness.py` |
| Checklist benchmark | The M12 benchmark, now on every line of the four checklists (291 lines instead of 107). | `scripts/checklist_benchmark.py` |

## What was wrong, and what I did

| Defect found | Effect | Fix |
| --- | --- | --- |
| Two checklists draw their bullets with a symbol font (Wingdings), so the bullet arrives as a private-use character that was not recognised as a list marker | Eight separate requirements were read as one clause. Bloomfield Hills was 15 clauses, St. Petersburg 27. The "bundle" lines of M12 were mostly this defect, not real bundles | Symbol-font bullets are list markers. Bloomfield Hills is now 93 lines, St. Petersburg 132 |
| A line that starts with a clause number inside a sentence ("... the requirements of / 233.3.1.1 and 233.3.1.2 shall apply") started a clause | Sentences cut in two, clauses that start mid sentence | A reference at the start of a wrapped line continues the sentence. Clauses starting mid sentence: 94 before, 20 after |
| A heading in ordinary type ("Junctions and cavity closures") became the last line of the clause above it | A foreign title inside the previous requirement | Such a line is a heading, and each clause now records the heading it sits under (`scope`) |
| A list item cut by a page break ("... operable window or exterior" / "door approved for emergency egress") became two clauses | A requirement without its second half | An item that stops without a full stop is joined to a paragraph that goes on in lower case |
| Numbered lists "1. ... 2. ..." whose items start in lower case were taken for wrapped lines | Lists lost | A number that is the next in a running sequence is a list item |
| "Hallways must be min. 3' wide" lost its first words | `strip_title` read "Hallways must be min." as a title | A title never contains a word of obligation or an abbreviation. The old "- " prefix had hidden this |
| Spreadsheets, csv files, web pages and photos of a page were not accepted | A checklist exported from Excel could not be used | Readers for them in `rules/readers.py`. Scanned PDF pages are read with OCR when they have no text layer |
| `csv.Sniffer` gives up on prose | A semicolon file was read as one column | The delimiter that cuts most rows into the same number of columns wins |
| An Excel workbook stayed open after reading | On Windows the uploaded file could not be replaced | The workbook is closed |
| A table row was read without its column names | "Bedroom \| 7 m2" says nothing about what 7 m2 is | A row is read with its header ("Room: Bedroom; Minimum area: 7 m2") |

## Results

Splitter audit on the nine real documents, old splitter against new:

| | Old | New |
| --- | --- | --- |
| Clauses starting in the middle of a sentence | 94 | 20 |
| Obligation sentences cut in two | 31 | 23 |
| Obligation sentences inside one clause | 3 455 | 3 461 (of 3 516) |
| Lines of the Bloomfield Hills checklist | 15 | 93 |
| Lines of the St. Petersburg checklist | 27 | 132 |

Format robustness (recall and precision of the clauses against the original, mean over 32 variants of four checklists): 0.956 and
0.980. Plain text, numbered text, Word, Excel, csv and web pages are at 0.97 or better. Before, Excel, csv and web pages were not
accepted at all, and numbered text scored 0.88 and 0.89 over the first variants. Scans are the weak spot: 0.57 to 0.84 recall
(the English OCR model drops accents, so the French scan is the lowest).

Checklist benchmark, local model qwen2.5:7b, on all 291 lines of the four checklists:

| | M12 (107 lines) | M13 (291 lines) |
| --- | --- | --- |
| Lines a plan can decide with today's facts | 7 | 10 |
| Of those, turned into a correct rule | 6 | 8 |
| Wrong rules on those lines | 0 | 0 |
| Rules written where none belongs | 1 of 100 | 4 of 281 on the first run, 1 after the fixes below |

The two decidable lines that stay open are honest declines: "1 egress door required min. 32 in." does not say which dimension of the
door the figure limits, and "Intended use of each room or space" is a noun phrase the model does not tie to "the room is named".

Reading the four rules written where none was expected: "Square Footage" became "every room has an area above zero" (invented),
"Dimensions" and "Dimensions from grade to finished floor ..." became "the drawing is dimensioned" (a weak partial reading), and
"Site Plan drawing's dimensioned with North arrow" became "the drawing is dimensioned" (faithful but only half the sentence). I
looked for a better strategy than another phrasing of the same question:

* A rule that only says a measured size is above zero can never fail, so the vacuity check now refuses it.
* One or two words with no figure and no word of obligation ("Dimensions", "Square Footage") are a heading or a form label. They are
  declined with that reason.
* A rule about the drawing as a whole that comes from a long sentence now says what it does not check ("any specific items the
  sentence names").
* The question "does the sentence require the drawing as a whole, or things shown on it?" separated 7 of 7 real sentences in both
  orders of the options. Asking "all or specific dimensions?" instead did not (it called "scaled and dimensioned floor plan" specific),
  so I kept the first.

After these changes the decidable lines are unchanged (8 of 10, 0 wrong) and the rules written where none belongs are 1 (the
half-faithful one). I checked the other three lines individually.

Most lines in the four checklists are not decidable from a plan today, so the reason shown for a declined line matters. Of 46 lines
about a plan the model does not record, only 6 ended with a reason that named the missing fact. A declined clause now also carries one
short phrase on what it seems to need, from one extra model call ("fire rating of the door", "stair landings", "alarm symbols"). On
the 22 such lines I printed, the phrase agreed in substance with my hand label every time (judged by eye, not scored). It only
explains: the clause stays declined and no verdict depends on it.

## Losses I accepted

* Two words or fewer with no figure are always a label. A two word imperative ("Dimension rooms") would be declined as one.
* A figure with no "at least" or "at most" takes its direction from the model when one order of the options names it and the other
  abstains. A model that is wrong in both orders is still wrong: "Ceiling height shall be 2.4 m" is read as a maximum by the 7B model.
  The rule carries the note that the direction was not written. I tried asking "would more comply, would less comply" as well; the
  model answers "no" to both for every sentence, so those votes carry nothing and were removed.
* Table detection has a 150 second budget per document, so on a slow or busy machine the later pages of a long standard can be read as
  plain text instead of as table rows. The result depends on the machine. It is the one non repeatable step left.
* Scans: OCR output is read as text and not checked against the page. The English model drops accents.

## Still open

* "See Table B4" cannot resolve when the table is a drawing: 37 of 119 references in the UK volume are unresolved. They are listed as
  unresolved on the rule, not guessed.
* The labels are by one person, and two documents were labelled again after their ids changed. One synthetic plan was used.
* Most numeric clauses of real codes (clear floor space, thresholds, reach heights) are about things the plan model does not carry.
  Reading is not the bottleneck for those: facts are.
* A hosted model has not been run on this code. The Groq allowance is the limit (see `docs/RUNBOOK.md`).

## Reproduce

```powershell
python scripts\split_audit.py data\real_docs --json reports\split_audit.json
python scripts\format_robustness.py
python scripts\checklist_benchmark.py --out reports\benchmark
```

The labels are in `benchmarks/checklist_labels.json` (document names, clause ids and labels only, never document text). A document can
carry a `_default` label that every line not listed receives.
