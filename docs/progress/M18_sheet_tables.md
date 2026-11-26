# M18: every table on a sheet, any columns (step 3, schedules part)

I built the schedules part of step 3 of `docs/PLAN_general_reviewpulse.md`. Until now we read one column of one table: the fire
rating of a door schedule, found by the column name. Now every table on a sheet becomes rows of one kind of thing (doors, windows,
rooms, finishes, fixtures, walls), each column is typed by the meaning of its header, and each number is read with its unit.
Everything is in `src/reviewpulse/schedules/`. I did not touch an existing file.

## What it does, in plain words

1. **Find the tables.** From the words of a page (PDF, or the text of a Sheet): a line of words is cut into cells where the gap is
   wide. A line whose cells name at least two different meanings is a header, and the lines under it that line up with its columns
   are the rows. For a PDF page I also take the tables drawn with ruled lines (pymupdf, rules only, no layout model), and I put
   the words of the file into each ruled cell myself. A table found both ways is kept once.
2. **Type each column by its header.** `vocabulary.yaml` lists header words by meaning (tag, width, height, sill, fire rating, area,
   floor finish, quantity, power and about 30 more) in English, French, German and some Spanish. Words are the default and need no
   model and no GPU. A bge-m3 match through the local Ollama is wired in as a second chance for a header the words cannot place,
   but only when `REVIEWPULSE_EMBED` is set to `on`; I have not run it (see losses).
   The cells have a say: a header that names a length over cells that are words is not typed ("Plafond" over "Platre" is a ceiling
   finish, over "2.7" a ceiling height), and a header made of a short word inside a longer one ("Bottom of Glass") does not take
   the meaning of the short word.
3. **Read each cell with its unit.** The unit comes from the header ("Width (mm)", "Area [m2]", "Width, cm"), else from the cell
   ("900 mm", `3'-0"`, "12 SF"), else it is guessed from the size of the numbers and marked `inferred` with a lower confidence.
   Units are symbols of `interpreter/units.yaml`, so `convert` and `to_si` work on every candidate.
   A fire rating cell ("1 HR", "45 MIN", "1-1/2 HR", "EI 30", "F90", "NR", "-") is read as minutes by the existing
   `parse_fire_minutes`, with the unit of the header when the cell is a bare number.
4. **Say what the table is about.** The kind comes from the title above it ("DOOR SCHEDULE", "TABLEAU DES FENETRES", "RAUMBUCH"),
   the tag prefixes (D, W) and the columns that point at a kind (a fire column points at doors). One of these alone is not enough:
   a table with no clear kind is `other`.
5. **Bind rows to drawn elements.** A row has a key: the tag column, else the room number, else the first column when it holds
   short distinct tags. `D-12`, `d12` and `D 012` are one key (the existing `tag_key`; a bare number loses its leading zeros).
   `bind_to_elements(candidates, model.elements)` sets `element_id` when exactly one drawn element of a matching class has that tag.

The output is a plain dataclass, `Candidate` (value, unit, meaning, entity kind, entity tag, sheet, table, row, cell text, header
text, unit source, confidence, value in SI, element id). It depends on nothing of the ledger, so a ledger can take it field by field.

```python
from reviewpulse.schedules import read_pdf_tables, door_fire_rows, bind_to_elements
tables = read_pdf_tables("set.pdf")                 # or read_sheet_tables(sheet)
cands = [c for t in tables for c in t.candidates]
door_fire_rows(tables)                               # {"D1": 60.0, ...} minutes, the old special case
```

## The door fire rating as a special case

`door_fire_rows(tables)` is the general path filtered to the meaning `fire_rating` of door tables. Compared with the old reader
(`annotate/schedules.py`) on the same text:

| | planted door schedules (120 tables, 722 fire cells) | real sets, 32 pages that mention fire or rating |
|---|---|---|
| old reader, right | 154 | rows found: 0 |
| old reader, wrong | 0 | |
| general path, right | 722 | rows found: 52 |
| general path, wrong | 0 | |
| right in the old reader and lost by the general one | 0 | 0 |

So there is no regression: everything the old reader got right, the general path gets right (and the old reader's rows are a
subset). The old reader only understands a few English and French header words in a fixed pattern. The 52 real rows are the door
schedules of the Rebuild Florida set (the same plan four times); their fire label cells hold "-", read as 0 minutes (not rated).
I read a few of those cells by eye, I did not check all 52. The Austin door schedule has no fire column.

## Numbers

No labels. Planted tests are PDFs I draw with pymupdf with the truth kept aside; the real sets are read and sampled by eye.

**Planted schedules** (360 PDFs: doors, windows, rooms, finishes, fixtures; en, fr, de; mm, cm, m and feet-inches; unit in the
header or in the cell; ruled or not; two-line headers; a width and height in one "Size" column; columns shuffled; a column
dropped). 8661 true cells.

| header pool | cases | recall | precision |
|---|---|---|---|
| headers a drawing commonly uses | 306 | 100.0 % (7170 of 7170) | 100.0 % |
| headers chosen outside the vocabulary ("Opng", "Ht", "UL Label", "AFF", "Classement") | 54 | 29.8 % | 95.9 % |
| all | 360 | 87.9 % | 99.8 % |

Read this carefully: I wrote the first pool with the vocabulary in view, so 100 % says the reader is complete on what the
vocabulary knows, not that it generalises. The second pool is the honest test of the words alone, and it is poor: 29.8 %. A header
no word list knows ("Opng") is not typed. That is what the embedding match is for; I could not measure it (no model server was run).

By language (all headers): en 91.2 %, fr 89.7 %, de 83.4 % recall; precision 99.5 % or more everywhere. By kind: doors 81.2 %,
windows 82.4 %, rooms, finishes and fixtures 100 % (the doors and windows lose cells to the wild pool, which only covers them).

**Against the simpler baseline** (column-name matching only, which is the reader we have: `annotate/schedules.py`, run on the same
doors and windows PDFs, the fields it can produce: width, height, sill, fire rating, quantity, type):

| doors and windows, 211 PDFs | baseline | general |
|---|---|---|
| common headers (157 PDFs) | recall 19.7 %, precision 86.9 % | recall 100.0 %, precision 100.0 % |
| outside the vocabulary (54 PDFs) | recall 0.0 % (nothing emitted) | recall 25.9 %, precision 100.0 % |
| all | recall 14.6 %, precision 86.9 % | recall 81.1 %, precision 100.0 % |

The general method wins on recall and on precision in both pools, and loses nothing the baseline had. Kept.

**Metamorphic** (doors and windows, changed in the words of the page and read again):
change one width cell to 777: exactly that candidate changes to 777 in 53 of 54 cases. Change the header unit from (mm) to (cm)
(or the reverse): the value stays, the unit changes and `value_si` is the converted value in 817 of 819 candidates. The failures
(1 and 2) are columns whose unit was not stated and was inferred, so there was no header unit to change. Imperial and metric agree:
`3'-0"` is 36 in and 0.9144 m (unit test).

**Real sets** (`data/real_plans`, every page; 0 tables means none found, not none present):

| file | pages | tables | rows | columns | typed with a meaning | with a unit |
|---|---|---|---|---|---|---|
| chief_architect_austin.pdf | 22 | 5 (3 ruled, 2 words) | 56 | 31 | 23 | 8 |
| rebuildflorida_floorplans.pdf | 57 | 26 (10 ruled, 16 words) | 154 | 200 | 140 | 16 |
| _chief_1_8, _chief_p5, austin_interior_remodel, millcreek_existing_proposed, nola_sketch | 15 | 0 | 0 | 0 | 0 | 0 |
| ch_zeichenhilfe_baugesuch, de_baugesuch_cleebronn, de_beispielgrundrisse_3raum | 32 | 0 | 0 | 0 | 0 | 0 |

(duluth_residential_samples.pdf is an empty file.) The Rebuild Florida set is one plan four times, so its 26 tables are 15 distinct
ones. Time: 18 s for the 22 Austin pages, 54 s for the 57 Florida pages, on the processor.

**Sample of every kind, read by eye** (15 distinct tables; right means kind, key, columns, units and cells are what a person
would read; partial means useful but something is wrong; wrong means it should not be there):

| kind | table | verdict |
|---|---|---|
| windows | Austin window and skylight schedule, 21 rows | right (the SIZE column "7060TC" is a catalogue code, left untyped) |
| doors | Austin door schedule, 13 rows | right for tag, quantity, width, height in inches; the FLOOR column (a level number) is untyped |
| fixtures | Austin cabinet schedule, 13 rows | right (kind "fixtures" is the nearest of my kinds) |
| fixtures | Austin plumbing fixture list, 2 rows | right |
| windows | Florida window schedule (type, count, model) | right, keyed by the type letter |
| other | Austin framing schedule | partial: the member NAME is typed as a room name (wrong), the rest is right |
| doors | Florida door schedule, 12 to 17 rows | partial: the group header "DOOR" is carried onto WIDTH and HEIGHT correctly; on some rows a height such as 6'-8" is cut by the cell border into "6' -" and `8" FIBERGLASS`, so that cell is lost; DOOR FINISH is typed as a material |
| finishes | Florida finish schedule (three variants) | partial: floor, base and wall columns typed, the ceiling material typed as a material, the room name typed as a remark |
| fixtures | Florida light fixture schedule | partial: type and notes typed, LAMP and CCT left untyped |
| fixtures | Florida air handling unit schedule | partial: a junk blank row from a second header line, most columns untyped |
| walls | Florida wall legend | partial: the kind is right, a data row was taken as header |
| other | Florida area legend ("Area Name", "Area Tag") | wrong: a symbol legend, not a schedule |
| other | Florida door and window schedules joined side by side | wrong: the words reader merged two tables that sit close together; the same tables are read correctly by the ruled reader |

Count: 5 right, 8 partial (counting the three finish variants), 2 wrong, of 15 distinct tables. The real precision is therefore
well below the planted precision, and I would not call the real result better than "usable with a check".

## What I changed on the way, because the real sets showed it

* pymupdf `find_tables()` in this environment calls a layout model; I pass `use_layout=False` so only ruled lines count. The model
  made each page 5 to 25 times slower and it is not something we need.
* The text pymupdf puts in a ruled cell was reordered ("2,40 m" became "240m ,"), so I fill each cell with the file's own words.
* A header made of a short word inside a longer one no longer takes that meaning ("Bottom of Glass" was typed as glazing,
  "Wall Description" as a wall finish); the one or two word generic nouns (wall, floor, ceiling, room, name, frame, leaf) type a
  header only when they are the whole header.
* A two-line header, a group header over sub headers ("DOOR" over "WIDTH") and a line of units under the header are merged.
* Abbreviation lists ("CLG - CEILING", "D - DEPTH") were first read as tables; a header over cells of the wrong kind is now not
  typed, and a table read from words alone must be mostly filled and carry something besides keys.

## Losses and what I did not do

* **Headers the words do not know are not typed** (29.8 % recall on the wild pool). The embedding match is written and gated but I
  did not run it: no model server, and I was told no GPU. Its gain is not measured and must not be assumed.
* **A length with no unit anywhere is guessed** from the size of the numbers (3.5 or less metres, 350 or less centimetres, else
  millimetres), marked `inferred`, confidence 0.6 times the header's. A US schedule with bare inches would be read as centimetres.
* **Cells cut by the drawing**: a value that overlaps a cell border is split between two cells in the real Florida door schedule.
* **Tables are found only with a header** that names two different meanings. A table with no header, or with headers of one meaning,
  is not read. Vertical text, rotated sheets and scanned or outlined text (needs OCR first) are not read.
* **Cells gaps**: two columns closer than 0.6 line heights merge into one cell; two tables closer than 20 line heights on one line
  are read as one.
* **Key and value lists** ("LOT SIZE: 22,225", the project statistics) are not tables with headers; they belong to step 4.
* **The Sheet and DXF adapter** (`read_sheet_tables`) is covered by the same code but I tested it only on a Sheet made from a PDF
  page, not on a DXF layout.
* I did not use the real sets as a score: there is no count of the tables that are present and missed. I looked for pages whose
  text names a schedule and checked the main ones (light fixture, air handling, cabinet); the exhaust fan schedule and the shear
  wall nail schedule of the Florida set are still not read (I did not look into why).
* The planted generator is mine. Its tables are regular and clean; real sets are harder, as the real table above shows.

## Files

* `src/reviewpulse/schedules/` : `vocabulary.yaml`, `vocab.py`, `values.py`, `reader.py`, `model.py`, `binding.py`, `door_fire.py`,
  `text_sheet.py`, `planted.py`, `__init__.py`
* `tests/unit/test_sheet_tables.py` : 47 tests (header meaning, units, cell values, planted en/fr/de ruled and not, metamorphic,
  imperial equals metric, door fire against the old reader, false-positive guards)
* `scripts/sheet_tables_audit.py` : `planted`, `meta`, `real`, `doorfire`

Run with `PYTHONPATH=src REVIEWPULSE_LABEL_LLM=0`; no GPU, no model server.
