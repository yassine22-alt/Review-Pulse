# M15: what the drawings say about a requirement, found for any clause in any language

This note is for someone who has not followed the project. M14 counted mentions of nine kinds of note, from a word list I wrote. That
works for the kinds on the list and for nothing else. This milestone replaces the list, for explanation, with a method that works for
any clause: find the note of the drawing set that is about it, check that it is, and compare its figure with the requirement's.
Every number below can be reproduced with the command at the end.

## What I looked for in the literature, and what I took from it

| Question | What I found | What I did with it |
| --- | --- | --- |
| How to find the passage that answers a regulatory question | Regulatory retrieval work (RIRAG 2025, ObliQA, RAGulator) reports the same thing in several places: fusing a word ranking (BM25) with a meaning ranking (a multilingual embedding model, bge-m3 being the usual one) by reciprocal rank fusion beats either alone, and a cross-encoder reranker (bge-reranker-v2-m3) that reads the requirement and each candidate together adds more on top. Query rewriting with a hypothetical answer (HyDE) is the other common addition | I built the fusion first, then measured it against the others (next section). The fusion alone turned out to be the weakest of the methods that use meaning, so the shipped method is the fusion followed by the cross-encoder |
| Can a small model be trusted to say whether a passage answers a requirement? | Not as a writer. In this project it is reliable only as a chooser, with the options shown in both orders (M11) | The model chooses among the best five passages, or none, in both orders. An answer that changes with the order is not believed |
| How to compare the figure of a note with the requirement's | Quantity extraction with units is a solved, deterministic problem; a model is only needed to decide which figure | The figures of both sentences are parsed with the unit table already in the project and compared exactly ("at least 20 min" against "60 minutes" agrees, against "15 min" contradicts) |

## What I built

* `annotate/passages.py` cuts the text of every sheet into passages a person would read as one statement: a numbered note, a legend entry,
  a callout. A long block is cut into its sentences, because the sentence that answers a requirement is outweighed by the block around it.
* `interpreter/drawing_evidence.py` retrieves (words, meaning, then a cross-encoder over the best twenty), verifies and compares, as above. It never decides a clause. It gives a person the note, its sheet,
  its words and its figure.
* In the app, a clause that no measured rule could be written for now carries this evidence, and the note appears in the clause's notes.
  `REVIEWPULSE_EVIDENCE=off` leaves it out, `REVIEWPULSE_EMBED=off` ranks by words only, `REVIEWPULSE_EMBED_MODEL` names another model.
* `scripts/evidence_eval.py` measures it on a real drawing set against every `needs_fact` line of the four checklists, with a test that
  needs no label: for every figure that agrees, the figure in the note is rewritten so that it breaks the requirement, and the comparison
  must say "contradicts".

## Which retrieval method: measured, not assumed

The first version used the fusion of words and meaning, as the literature suggests. I then built a test that needs no label
(`scripts/retrieval_eval.py`): for each of the 46 checklist lines the local model writes the note an architect would put on a drawing
to satisfy it, in English, French and German. That note is planted alone among the 584 real passages of the permit set, and each method
must find it from the requirement alone. The notes are written by a model, so they are closer to the requirement than a real note is:
the absolute numbers are optimistic and the comparison between methods is what counts.

| Method | Recall@1 | Recall@5 | Mean reciprocal rank | Recall@5 in English, French, German |
| --- | --- | --- | --- | --- |
| Words only (BM25) | 0.51 | 0.60 | 0.557 | 0.98, 0.48, 0.35 |
| Meaning only (bge-m3) | 0.67 | 0.86 | 0.754 | 0.93, 0.87, 0.78 |
| Words and meaning, fused by rank (my first version) | 0.52 | 0.72 | 0.616 | 0.98, 0.65, 0.52 |
| **Fusion, then cross-encoder (adopted)** | **0.71** | **0.88** | **0.786** | **0.98, 0.87, 0.78** |
| Same with a hypothetical note written first (HyDE) | 0.69 | 0.86 | 0.764 | 0.98, 0.87, 0.74 |

What this shows:

* The method I had shipped, the fusion, is worse than meaning alone once the requirement and the drawings are in different languages. A
  French requirement shares no words with an English note, so the word ranking only adds noise to the fusion. In English alone the
  fusion is fine (0.98).
* The cross-encoder repairs it and is the best on every measure, with no loss in any language. On the 6 real notes I had read, words
  alone find 4 and every method that uses meaning finds all 6 in the first five.
* HyDE did not help (0.86 against 0.88) and costs one more model call per clause, so it is not adopted.
* The cross-encoder costs 570 MB of disk and about 0.2 seconds per clause on the processor. Without its files, or without the
  `tokenizers` library, retrieval falls back to the fusion and the app still runs.

## What I found while building it

| Finding | What I did |
| --- | --- |
| The notes are written in blocks of several sentences, and a single embedding of the whole block hides the one sentence that matters | Long blocks are cut into sentences before retrieval |
| A note with two figures of the same kind ("min. width of 34 in. Hand rails may encroach a max. of 3 1/2 in") gave the model both figures in every option, so it could not tell the options apart | Each figure is shown with its own words only |
| A 7 billion parameter model answers "no" to every yes/no question about a figure, whatever it is shown (6 of 6 cases, including the 3 correct ones) | A lone figure of the right kind is accepted as it is, and the check says that it is the only figure of that kind and shows its words. Among several figures the model chooses in both orders, which works (it picks 34 in for the stair width) |
| The embedding model on the same graphics card as the reading model would push it out of memory at each clause | It runs on the processor by default; one sentence takes well under a second |

## Results

Real drawing set: a US permit set (22 sheets, 584 note passages). Requirements: the 46 lines of four real checklists that my labels
mark as "about the plan, but the plan lacks the fact". No label was written for the notes.

Every step is the same 46 lines against the same 584 passages, read by the same local model:

| Retrieval and choice | Lines with a note | Read by me: right / partial / wrong |
| --- | --- | --- |
| Words only, note chosen in two orders | 9 | 9 / 0 / 0 |
| Words and meaning fused by rank, two orders (first version) | 11 | 8 / 2 / 1 |
| Plus cross-encoder, top five, two orders | 13 | not read |
| **Plus cross-encoder, top three, majority over rotations (adopted)** | **17** | **14 / 3 / 0** |

The three partial notes: "stairways must have a light, three-way switch" got the legend of switch types; "location of exhaust fans" got the
note about venting them; "window and door size and proper location" got the egress window dimensions. The 14 right ones include the
fire rating of the door between garage and house, smoke and carbon monoxide detectors (a note that sits in the middle of a paragraph
of electrical notes, found by cutting long blocks into sentences), guards, handrails, baluster spacing, safety glazing, non bearing
walls, the sheet size, and the stair width.

Two things to know about the steps. First, the cross-encoder alone raised the count from 11 to 13 and lost five lines: it ranked the
right note first for the garage door line but the model's "same answer in both orders" rule then rejected it. The model leans towards
a position when it is unsure, so the rule now asks the question once per rotation of the three notes (each note in each position once) and
believes a majority. That recovered those lines and added four more. Second, the cross-encoder's own score cannot decide a match: on
this set correct notes scored from -2.7 to +2.2 and wrong ones up to +4.2, so it shortlists and the model confirms.

One line is still lost compared with the first version: "door to attached garage must be a 20-min. door" shows the right note as the
first of three, but no majority chooses it, so its figure (60 minutes meets 20) is no longer compared. The same note is found for the
sibling line "type and fire rating of door separating garage and house", with no figure to compare. This also means the planted
contradiction test of the figures has no case left on this set (it had one); the comparison itself is covered by unit tests on real
wording. The one real contradiction remains: the checklist asks for a 3 ft stair and the permit set's own note says 34 in, two codes
that differ. The tool quotes both sides and leaves the decision to the reviewer.

### Two more real drawing sets

The method was not changed after the first set. I then ran it, unchanged, on two other real sets, with the same 46 lines.

| Drawing set | Passages | Lines with a note | Read by me: right / partial / wrong |
| --- | --- | --- | --- |
| US permit set (the set it was built on) | 584 | 17 | 14 / 3 / 0 |
| A Florida residential drawing set, 57 pages, a different layout and authors | 1 080 | 16 | 11 / 4 / 1 |
| German and Swiss permit documents (a drawing guide and a permit file, written in German) | 193 | 3 | 0 / 1 / 2 |

The Florida set is the fair test: new notes, new wording, and a set more than three times bigger. 11 of the 16 notes are about the line
(the emergency escape opening rule R310.1, smoke alarms R314.3, combination smoke and carbon monoxide alarms, the landing rule R311.3,
the drawing scale, the handrail note, treated wood stairs with the number of risers to verify). The four partial ones are a light
fixture legend for "stairway light", a keynote list with a pull down stair for "attic access", a note on load bearing wall material for
"indicate load bearing walls", and a ceiling height schedule heading for "room dimensions and ceiling heights". The wrong one is the
attic ventilation note for "attic access opening dimensions".

The German and Swiss set shows what the tool does when the drawings do not contain the answer. These documents are a guide on how to
draw a permit application and a permit file with room labels: there are no notes about alarms, fire ratings or handrails to find. The
right answer for almost every line is "no note", and 43 of 46 lines say so. The three notes it did choose are weak: "planned sleeping
room" for a carbon monoxide detector, a sentence on how to draw stairs twice in a plan for "stairs and landings" (the closest to
relevant), and a section heading for "plumbing fixtures". So on a set with no answers the false match rate is 2 of 46 lines, which is
the cost of letting the model choose. A person reads the quoted note and sees at once that it is not about the line, but it is noise.
The requirements were in English and the notes in German, and the cross language retrieval worked as intended (the planted note test
above); this set could not show more, because it holds almost nothing to find.

## Losses I accepted

* A lone figure is taken as the figure of the requirement. A lone length can be another property (a door's thickness for its width). The
  words around the figure are shown for exactly this reason, and the result is evidence for a person, never a verdict.
* The embedding model (`ollama pull bge-m3`, 1.2 GB) and the cross-encoder (570 MB) have to be installed. Without it a requirement in another language than the drawings
  finds little, and lines whose words differ from the note's are missed.
* The notes are read from the text layer. Text drawn as outlines on a vector sheet, and drawings that are scans, give no passages.
* The numbers of the last table come from one drawing set, and the "right, partial, wrong" columns are my reading of each note against
  its line. The first column is a count and needs no judgement.
* Retrieval over one drawing set was checked by reading. The evidence is only as good as the wording the set happens to use.
* A checklist from one jurisdiction against drawings from another can contradict legitimately (a 3 ft stair against a 34 in stair of
  another code). The tool reports the difference and quotes both sides; whether it matters is for the reviewer.

## Still open

* Three real drawing sets were read, but only one of them in German and with almost nothing to find. A German or French set with written notes about safety provisions is still needed to measure cross language evidence on real notes.
* Retrieval is not tuned: the number of passages shown to the model (five) and the fusion constant are the usual defaults.
* Symbols with no words beside them are still not found.
* A hosted model has not been run on this code, and the labels are by one person.

## Reproduce

```powershell
ollama pull bge-m3                                                   # once, for meaning as well as words
pip install tokenizers                                               # once, for the cross-encoder
python -c "from reviewpulse.interpreter.drawing_evidence import fetch_reranker; print(fetch_reranker())"   # once, 570 MB
python scripts\retrieval_eval.py --plans data\real_plans\your_set.pdf --out reports\retrieval   # compares the methods
python scripts\evidence_eval.py --plans data\real_plans\your_set.pdf --out reports\evidence
$env:REVIEWPULSE_EMBED = "off"; python scripts\evidence_eval.py --plans data\real_plans\your_set.pdf --out reports\evidence_words
```
