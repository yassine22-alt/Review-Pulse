# What real documents and real drawings showed (November 2026)

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md).

Until now ReviewPulse was tested on documents and plans that we wrote or generated. This page records the first test on
documents and drawings written by other people. It is not a success report. It lists what broke, what was fixed, what was
measured, and what is still open. The real files are public documents downloaded for local testing and are never committed
(`data/real_docs/` and `data/real_plans/` are ignored).

## What was tested

- **Requirement documents:** the US 2010 ADA Standards (300+ pages), the UK Approved Document B volume 1 (fire safety), three
  French accessibility texts (a ministerial order, a regional architects' guide, a quality-agency sheet).
- **Drawings:** a 22 sheet permit set of a house (Chief Architect sample), a 57 sheet hurricane-recovery sample set (Rebuild
  Florida), a one page municipal floor plan example, two hand sketches.

## Requirement documents: what broke and what was fixed

| Finding | Fix |
| --- | --- |
| Reading a 14 page PDF took 26 s, a long standard would have taken about an hour: the table finder ran on every page | Pages with no ruling lines cannot hold a ruled table and are skipped (exact). A 90 s budget bounds the rest, and the reader says which pages were not scanned |
| Lists lost the sentence that introduces them ("must have the following characteristics:") | A list with no numbered parent hangs from its introducing sentence |
| A list item swallowed the paragraph that followed it | An item ends at the first blank line, and PDF text blocks keep their paragraph breaks |
| Repeated numbers under different articles were told apart by "[dup] #2" | They are told apart by the article they sit under ("1 [Art. 5]") |
| The preamble of a document was offered as requirements | Unnumbered text needs an obligation word, not just a digit |
| Every definition of the document was added to every clause (slow, distracting) | A definition travels only with clauses that use its term |

## Drawings: what broke and what was fixed

- **Elevations produced rooms.** On the 22 sheet set, two elevation sheets produced 58 and 114 "rooms" and a third 68. Nothing
  recognised that a sheet was not a floor plan. A sheet recogniser now names each sheet (`annotate/sheet_kind.py`): a vision
  model looks at the whole sheet, with a title-words fallback when no vision model is reachable. Only a floor plan sheet is read
  as one; every other sheet is named and gives no rooms, openings or routes.
  - Measured on 21 real pages whose kind I judged by eye: the vision model says "floor plan or not" correctly on 20 of 21 and
    finds all 4 real floor plans; the old behaviour (rooms found means plan) was correct on 9 of 21 and the title words on 11
    of 21. The exact kind is right on 20 of 23. The sample is small and comes from four documents.
  - The vision model's extra "a floor plan appears somewhere on the sheet" flag is not used: it wrongly admitted 4 more sheets.
  - On the whole 22 sheet set the gate leaves 6 sheets treated as floor plans and 19 rooms, instead of over 260.
- **A multi sheet upload was read from its first sheet only** by the rule reading screens (the cover page). It now reads a floor
  plan sheet: the one that reaches the outside, otherwise the one with most rooms.
- **A level cannot prove "no route to the exit".** On a set with several floor plans, a level with no door to the outside leaves
  the building by stairs the drawing does not link. "No route" is no longer claimed there even when the reviewer confirms
  every room and door was found.
- **Open, large:** on the real first floor plan the wall finder misses most interior walls (drawn as double lines with
  fills), so rooms merge and only 4 are found where a person sees about 15. The sheet is marked lowest trust, so nothing is
  reported as passed, but nothing useful can be checked either. This is the largest remaining gap on real drawings.

## Reading real clauses: the serious finding

20 clauses sampled at random from a real French accessibility guide and 20 from a French ministerial order were read on a
plan. One of each became a checked rule; the others were reported as not checkable with a reason. Reading them, most of the
refusals are right (parking, door handles, sockets, thresholds: a plan does not show them) and a few are clauses a plan could
decide but a 7B model could not turn into a rule (lists whose subject is in the introducing sentence).

**One of the two rules that were written was wrong:** "the sockets must be less than 1.30 m above the floor" became "for every
room, the travel distance to the outside is less than 1.3 m". It has the sentence's number, its direction and a fact that
exists, so every check passed. The word-grounding check that should have caught it only knows English. A rule like this would
report false violations in production. This is the failure that matters most, and it is being addressed first (see below).

## What was tried against the wrong-rule failure, and what was kept

The check "does the rule measure what the sentence limits" must work in any language and any domain. The test is annotation
free: on the 250 synthetic clauses (English and French, many domains) the true rule is compared with the same rule whose
measured fact is swapped for another fact of the same unit (`scripts/grounding_swap.py`, `scripts/grounding_choice.py`).

| Method | Result | Decision |
| --- | --- | --- |
| Similarity between the sentence and each fact description, three multilingual embedding models | Separation (AUC) 0.82 to 0.87 for plain relatedness, 0.61 to 0.64 for a swapped fact (French worse than English) | Not used: rejects about 20% of wrong facts at best |
| An off-the-shelf multilingual entailment model, sentence against a plain reading of the rule | AUC 0.63 on swapped facts | Not used |
| **Multiple choice by the local model:** "which of these facts does the sentence limit, or none?", asked independently of the draft, retried once with the options reversed | Agrees with a true rule 58 of 63 (92%; English 25/28, French 33/35). Rejects a swapped rule 54 of 54. Never picks a fact that was removed from the list (63 of 63). The real socket sentence gets "none" in French, English and German | **Kept**, on by default (`interpreter/grounding.py`) |
| The same, with a longer instruction naming the object as well as the measure | Agrees 87%, rejects swapped 96% | Rejected: worse on both, kept the shorter prompt |

Cost of the kept check: about 8% of correct rules are refused (they come back as "not checkable" with the reason shown, never
silently). Remaining weakness: for 4 of 8 sentences about something no plan fact measures (door handle height, threshold
height, handrail height), the model picks a related fact such as the door height, so a rule measuring that would be accepted.
The reviewer's approval is the last guard there.

On the real French guide the wrong socket rule and a second wrong rule (counting connections for a circulation-width
sentence) are now refused.

## Reading long documents without waiting hours

- **Triage before drafting** (`interpreter/triage.py`, used by "Read all clauses"): one short yes or no per clause, "can a plan
  show this?", understood in any language. Measured: keeps 54 of 60 checkable clauses (90%) and drops 20 of 20 sentences about
  permits, fees, materials, signage and dates in five languages. The loss is the 10%: a dropped clause stays in the list with
  its reason, and reading a single clause never uses triage, so a reviewer can always read it anyway.
- **The document is split once** and remembered per project (`rules/clauses.py: split_cached`). Before, every click re-read the
  whole PDF; the ADA standard took 278 s to upload and then minutes per clause. Clauses read in parallel (hosted models) write
  the cache concurrently, which crashed a test on Windows; fixed with one temp file per writer and a regression test.
- **Slot filling** (`xeval/slot_arm.py`): for a plain limit on one quantity the model only chooses (kind of thing, quantity,
  categories) and a program writes the rule from the number and wording of the sentence. On the synthetic corpus it applies to
  15% of clauses (9 of 60) and is right on 8 of 9, with the free-form arm right on all 9: no gain there, and one wrong rule
  accepted. It is left on because real clauses differ (see next) and every rule it writes goes through the same checks; this is a
  judgement call, flagged for review.

## How many real clauses can be checked at all

Counting by program (no model): of the clauses that contain an obligation word and a figure, only 24% of the French guide, 0%
of the French ministerial order, 0% of the sheet from the quality agency and 1% of the UK fire safety document are a plain limit
on one quantity. Most of a real regulation is conditional, compound, or about something a plan does not show.

Reading the plan-checkable clauses of the French guide and order (the ones a person would say a plan can decide) with the local
7B model: 2 rules were written from 7 clauses. One is correct ("largeur minimale des circulations intérieures de 0,90 m" became
a corridor minimum width rule). One is a loose proxy ("a clear space of 1.50 m in front of the fixtures" became "kitchen
minimum width at least 1.50 m"), the kind of nuance no automatic check can catch and the reason approval stays mandatory. The
others failed on sentences with two limits, a garbled number, or a quantity the plan does not provide (clear passage width at a
90 degree opening).

**Conclusion for now:** with a 7B model on a 6 GB laptop GPU, the automatic yield on real regulations is low and every rule
still needs a human. The checks make sure that what is written is not silently wrong in the ways measured here. The yield is
expected to be higher with a hosted model, but that has not been measured because no key was available here. The commands to
measure it are in `docs/RUNBOOK.md` section 6b.

## Smaller fixes found while doing this

- A hosted backend whose settings were incomplete made the health check fail instead of showing "unavailable".
- Naming a model for the hosted client dropped the rest of the settings (the key).
- `REVIEWPULSE_LLM` in the `.env` file was ignored (only the real environment was read).
- French wording tables lacked "minimale" and "maximale", the forms real texts use.
- A list item now carries the sentence that introduces its list into what is read and checked.
- An auto-fixer run over the scripts folder touched ten unrelated files; they were restored.

## Still open

- The wall finder on drawings in styles it was not built for (the largest gap: 4 rooms found on a plan with about 15).
- The local model's yield on real clauses (above); the hosted option is built and tested against a mock provider, not measured.
- A drawing set's levels are not linked, so routes between levels are not checked.
- Hand sketches and scanned drawings are not machine read.
- The vision model takes about 10 to 40 seconds per candidate sheet on this laptop GPU; a 22 sheet set took 14 minutes with the
  model shared with another job. Sheets with no walls found are not sent to it.
- The "kind of thing" question of the slot arm and the grounding check were measured on synthetic domains and a few real
  sentences only; they need a larger real sample, with a person judging, to be trusted.
