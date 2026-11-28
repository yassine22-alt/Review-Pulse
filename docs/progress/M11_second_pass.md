# Second pass on real drawings and real requirements (November 2026)

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md).

This page records the second round of work after the first test on documents and drawings written by other people
([M10_real_world_findings.md](M10_real_world_findings.md)). It lists what was changed, how each change was measured, what was tried
and rejected, and what remains. The statement of what the tool does well is in [../SCOPE.md](../SCOPE.md).

## How the work was done

Each problem was stated in general terms, the literature was searched for methods
([M10_literature_sweep.md](M10_literature_sweep.md)), and each candidate was measured on data nobody tuned it on. A change was kept
only when the gain clearly outweighed the loss; every loss is listed here. Four evaluations were added or repaired:

- `scripts/room_stress.py`: room finding when walls are missed, on 150 public plans with known rooms, tested on a second sample of
  150 other plans after the choice was made.
- `scripts/relations_eval.py`: requirements about how spaces connect, 16 sentences in four languages plus 6 that are not relations.
- `scripts/grounding_concern.py`: the check of which kind of requirement a sentence states.
- `scripts/review_pack.py`: real drawings, the original page next to what was found, with strict verdicts.

## Drawings

| Problem found | Change | Measured result |
| --- | --- | --- |
| Feet and inches were not read at all, so a US drawing had no scale | Dimension text such as `12'-6"` and `15'-0 1/8"` is parsed; written scales (`1/4"=1'`, `Maßstab 1:100`, `Escala`, a bare `1:100`) are read in several languages | The complex US sheet went from no scale to 1:48 |
| Scattered dimension pairs were accepted as a scale (ratios from 4.7 to 222 gave a confident 1:100) | Inliers must lie within 4% of the median | Scattered evidence now gives no scale |
| A written scale can be wrong (a page fitted to the paper) | When at least five rooms with a printed area agree within 4% on a scale that differs by more than 6%, the printed areas are used | On a German plan the written 1:100 was off by 8%; all 12 labelled rooms then match a dimension printed inside the room (a living room of 3.86 by 4.52 m against 385 by 451 cm printed). That check uses numbers other than the areas |
| Rooms merged into one blob when a wall was missed | Each room name is a seed; free space is divided among the seeds by flooding over the distance to the walls; the outside competes as one more seed; each piece must be mostly enclosed | The complex US sheet went from 2 rooms to 12 rooms with a printed area, 11 within 50%. Controlled test below |
| Door swings drawn part-open (45 degrees) were rejected | A swing of 30 degrees or more is accepted when a leaf line of the same length is at the hinge | Doors found on the complex US sheet: 1 to 9 |
| Text drawn as outlines was unreadable without a heavy OCR install | A RapidOCR backend (PaddleOCR models on onnxruntime, no PyTorch) | 62 words in about 30 s on CPU; room names and areas were then attached |
| An inferred room boundary could produce a failure | Room sizes and connections that come from label splitting are untrusted facts: they can warn, never fail | Unit test |

### Controlled test for missing walls

Plans from the public ResPlan dataset (true rooms known), a room name written at every true room, and `g` random wall gaps. Second
sample of 150 plans, not used for any choice:

| Gaps | Plain: precision, recall, F1 | With room names: precision, recall, F1 |
| --- | --- | --- |
| 0 | 0.991, 0.994, 0.993 | 0.889, 0.991, 0.937 |
| 2 | 0.980, 0.761, 0.857 | 0.878, 0.839, 0.858 |
| 4 | 0.964, 0.567, 0.714 | 0.882, 0.826, 0.853 |
| 8 | 0.905, 0.320, 0.473 | 0.863, 0.803, 0.832 |

Kept. The loss is on clean plans: an open plan with two named areas is divided in two (about 11% more rooms), which is flagged as
inferred. **Tried and rejected:** returning a cut to one space when its edge is wide compared with the pieces, on the idea that a
missed wall leaves a narrow gap and an open plan a wide edge. The gaps left by missed walls were as wide as open plan edges; at
the best threshold recall at 8 gaps fell to 0.18, below the plain method. The code was removed.

## Requirements

| Problem found | Change | Measured result |
| --- | --- | --- |
| A clause about amusement ride clearance became "every room has a route to the exit" and passed every check | A second multiple choice check: which kind of requirement (route, link, count, yes or no fact) does the sentence state | A true kind is accepted 90 of 100 times, a wrong kind rejected 97 of 100, sentences no plan shows rejected 30 of 32 |
| The new check refused good route rules because the plan's own "has a route to the exit" fact and the generic kind were both offered | A choice from the same family counts as agreement (routes, links, connection counts) | Art. 2 and Art. 2.1 of the example document are drafted again |
| Connection requirements were written badly by the 7B model (invented quantities, lost "not") | A relation arm: the model chooses the kind of relation and the spaces (one category per side, with a yes or no for a space that is both subject and to be avoided); a program writes the rule | 16 sentences: 11 right, 5 declined to the general arm, 0 wrong accepted; 6 non-relations all declined. A planted garage-to-bedroom connection is now detected, which it was not |
| Sentences in German and French were refused because "Küche" and "séjour" never matched the accent-free category labels | The sentence is folded to plain letters before the comparison | Affects every drafting arm; links in German went from declined to right |
| Dual units ("54 inches (1370 mm)") confused the number check | The imperial equivalent is dropped before the model reads the clause | Unit tests; no measurable change on the real clauses sampled |
| Table reading stopped at a time cap (pages 130 to 279 of the 280 page standard were not scanned) | Pages are read in worker processes; the cap is a wall clock limit of 150 s | All 279 pages in 112 s with 6 workers (628 s of work). A filter on line counts was tried and rejected: it missed 4 of 32 table pages |

### Yield on real regulations

The same 20 random clauses of a real French accessibility guide that gave one rule in the first round now give none, and that one was
wrong (a socket height rule that had become a travel distance rule). A second French text gives one rule, a loose proxy (kitchen
minimum width for a clear space in front of fixtures). Nothing in the first sample is something a floor plan could decide, so zero is
the right answer. This is the central limit of the tool and is stated in [../SCOPE.md](../SCOPE.md): most of a real regulation is not
about facts a plan carries.

### Measurement problems found and fixed

- The relational evaluation created projects without a rule pack, so its reference engine silently found nothing. It now requests the
  built-in pack. With it, on ten generated plans (eight with a planted error), the new rules report a violation in 9 of the 13 cases
  where the reference engine finds one, and raise no false alarm on clean plans.
- The room splitting broke a golden snapshot on a rotated plan, because the name and area lines of a room were tested for stacking in
  page orientation, not along the text. Fixed and covered by a test.
- The self-check did not know the new OCR backend.

## Still open

- Scans, hand sketches and multi-level drawing sets are not read.
- The open plan cost above; a way to tell an open plan from a missed wall without more evidence has not been found.
- Rules for conditions, exceptions and several limits in one sentence.
- A hosted model has not been measured for want of a key.
- Door versus opening in a sentence is not distinguished when a rule counts connections; the reviewer's approval is the guard.


## Real checklists: what the arms did (measured)

I read plan-review checklists written by building departments (Allentown, Berkeley) through the product on a plan, with the local
7B model, and kept the trace of every arm for every line. Result of the last full run: 2 of 12 Allentown lines and 0 of 7 Berkeley
lines became a checked rule, before the fixes below. After them, on the lines that a plan can decide, the rules read as follows.

| Line of the checklist | Rule written | Judged by eye |
| --- | --- | --- |
| Habitable rooms min. 70 s.f. except kitchens, also min. 7' in any dimension | area at least 6.50 m2 and minimum width at least 2.13 m, on habitable kinds, kitchens excluded | faithful |
| Hallways must be min. 3' wide | minimum width of corridors at least 0.9144 m | faithful |
| Stairways must be min. 3' wide | minimum width of spaces labelled stairs at least 0.9144 m | faithful, an approximation of the stair width |

What kept the rest from becoming rules, in order of how general the cause is:

1. **Provenance.** Rules built by programs quoted the normalised sentence, so the quote was "not found in the clause". Now they cite
   the clause as written (`citation`). This alone had hidden every program-written rule on real documents.
2. **Word overlap.** The English word check refused "wide" against "width". Program arms choose facts from a list, so that check is off
   for them; the number, direction and category checks stay on.
3. **Category words with an ending.** "Stairways" did not name the category "stair". A category word is now also named by the word with a
   short ending (stems of four letters or more).
4. **Several requirements in one line.** "1 egress door required min. 32 in. Door must not require a key." is now read sentence by
   sentence; the first sentence that becomes a rule is kept and the others are listed as not checked, so the rule never reports
   "satisfied" for what it did not read.
5. **The plan lacks the quantity.** Window area (8 % ratio), emergency opening size, stair risers and treads, landings, handrails,
   smoke alarms, fire rating of a door, address numbers. These are reported as not checkable with the reason; no rule is invented.

Losses recorded: a stair width is approximated by the width of a space labelled stairs; a line with a figure and a negation in one
sentence ("must not require a key") is still read only for its plain part. Unit tests: 766 pass.
