# M17: fact requests and the evidence ledger (step 2 of the general plan)

Written 25 November 2026. Code: `src/reviewpulse/ledger/`. Tests: `tests/unit/test_ledger.py`.

## What I built and why

Until now a requirement could only use the facts that perception decided in advance to produce. Step 2 of
`docs/PLAN_general_reviewpulse.md` turns this around: the requirement asks, producers answer, a ledger decides what survives.
This note records what exists, what I measured, and what is still not wired in.

| Piece | File | What it does |
| --- | --- | --- |
| Fact request | `request.py` | A typed question: entity (or kind of entity), the property, the kind of value (number, bool, category), the unit, the dimension derived from the unit with `interpreter/units.py`, the words and clause it comes from, and a tolerance for "two numbers agree". |
| Candidate | `candidate.py` | One answer: value, unit, entity, the evidence kind (measured, stated, inferred, attested), a source that must be non empty, optional sheet, view, region and words, a score, and the reviewer's name when attested (a name is required). |
| Producer protocol | `producer.py` | `holds(request)` says by meaning how well the producer can answer (0 means not at all); `answer(request)` returns candidates. Meaning is the same name, or the same kind and dimension with every word of the request found in the property's name and description. |
| Ledger | `fuse.py` | Fuses candidates per entity and fact. Rules are listed at the top of the file and summarised below. |
| Adapters | `adapters.py` | The existing fact graph as four producers (geometry, schedule, notes, labels), a store of reviewer attestations, and `binding_request` for the properties the interpreter already declares. |
| Back to the interpreter | `inputs.py` | `requests_for_program` reads the typed questions out of a rule; `inputs_from_resolutions` turns the ledger result into the `Inputs` the evaluator already reads; `ledger_inputs` does it for a whole fact graph; `inputs_for_program` does it demand driven (only what the rule reads). |

### How the ledger decides

1. A candidate of the wrong kind of value or the wrong dimension is rejected and listed with the reason. It is never converted into
   something it is not. A number in a compatible unit (cm, ft) is converted to the unit of the request.
2. A reviewer attestation, which needs a name and a source, outranks everything. The values it overrode stay listed, with their
   sources, and appear in the fact's source text. Two attestations that disagree are a conflict.
3. Candidates that agree form a cluster. Producers of one family (one text layer, one model) count once; independent families
   combine as 1 - product of (1 - score), so agreement raises trust. A value is accepted at 0.8.
4. Clusters that disagree are a conflict. No value is chosen, not by score, not by order. Both sources are shown, and the fact
   reaches the rule as `conflicting`, so the rule is unresolved.
5. A value below 0.8 is unverified: kept and shown, never a pass.
6. Nothing answered is unknown. Unknown is never a pass, and `Resolution.followup()` gives the typed question that would settle it.

### Compatibility with the pending module on `origin/rule-interpreter`

Her ideas are kept, her file name is not used. `FactRequest` mirrors `EvidenceRequest` and `FactDeclaration` (entity, fact, unit,
reason, why, clause). `Candidate` mirrors `EvidenceEntry` (entity, fact, value, unit, source, reviewer); `kind` maps to her
`origin` through `ORIGIN_OF_KIND` in `candidate.py` (attested is `reviewer-attested`). Conflicting values stay conflicting and a
source citation is required, as in her `apply_evidence`. One difference: our `Fact` has no `origin` or `reviewer` field, so
an attestation is written into the source text ("attested by NAME: SOURCE"). When her `Fact` arrives, `Resolution.fact()` is the one
place to fill the two fields.

## What I measured

All numbers are from `tests/unit/test_ledger.py` (28 tests, 28 pass, ruff clean on the new files).

* **Planted value swaps.** A geometry value of 0.9 m against a schedule value of 0.7 m is a conflict with both sources in the
  text, the fact reaches the rule as conflicting, and the rule `forall doors: width >= 0.8 m` is UNRESOLVED. The same rule with the
  swap undone is SATISFIED, so the conflict, not the rule, caused the refusal. A producer with a higher score that disagrees does
  not win, in either order of producers.
* **Units.** 90 cm from a dimension string and 2.952756 ft from a schedule agree at 0.9 m and are resolved. A candidate in m2 for a
  length request and a boolean for a number request are rejected and listed.
* **Attestation.** It outranks a disagreeing producer and keeps the overridden value and source; a nameless or sourceless
  attestation cannot be created; two disagreeing attestations are a conflict.
* **Trust.** Two producers of one family at 0.6 stay unverified; two independent families at 0.6 give 0.84 and resolve.
* **No regression.** On the 13 generated demo plans of `synth/scenarios.py` (the same list as `tests/app/test_scenarios.py`),
  the fact graph read through the ledger gives `Inputs` identical to `factgraph.convert.to_inputs` (all 1999 facts, compared as full
  dumps), and six rules (door width, bedroom size, living area, exit distance, windows, fire doors where the plan has a schedule) give
  identical full results (outcome, trace, evidence) in 65 runs, both with the whole graph and demand driven. Scenarios 02, 10, 11, 12,
  13 violate the door rule as planted, 04 and 07 violate the exit distance rule, 08 is unresolved, as today.
* **Self check.** `python -m reviewpulse.selfcheck` still finds 3 of 3 planted errors on DXF, PDF and the web app. This is true
  by construction: I changed no existing file, so the check does not run through the ledger yet. The claim made by the regression
  test above is the one that matters for the ledger.

### A flaw the regression test caught

My first matching by meaning let the request "area_m2" also match the schedule's "window_area_m2" (every word of the request is in
that name). The ledger saw two different values for one room area and reported a conflict on all 7 rooms of plan 01. Two fixes, both
now tested: a property may not say more than the request does ("window_area" is not "area"), and a property of the exact requested
name outranks any match by meaning (the alias candidates are listed as rejected). A match by meaning also gets a score of
0.95 x 0.8 = 0.76, so alone it stays unverified until an independent family agrees.

### The alternative: one model call picks the value from candidate passages

I did not run it. There is no hosted or local model call in this step, by instruction, so I cannot claim numbers for it. What I
can say from the design: the ledger gives the same result on every case above without a model, shows both sources on a conflict,
and cannot pick a value silently. A model that chooses among passages can only be compared on a labelled set of conflicting
candidates, which does not exist yet. The ledger is the part that keeps the answer traceable, and a model can sit inside it as one
more producer (family "model", kind "inferred", score from its calibration) instead of being the judge.

## Losses and limits

* **Not wired.** No existing file was changed. No finding on a real review uses the ledger yet.
* **One family per fact today.** On the existing fact graph each fact has exactly one producer, so the fusion rules (agreement,
  conflict, attestation) are exercised by tests with stand in producers, not by real second sources. No new real producer exists yet
  (dimension strings, legends, vision model are steps 3 to 6).
* **Score thresholds are set by hand.** 0.95 for a trusted value, 0.5 for an untrusted one, 0.8 for acceptance, 0.8 discount for a
  match by meaning. They reproduce today's trusted flag exactly, but they are not calibrated probabilities. Step 6 of the plan
  covers calibration.
* **The three part split of today's facts is a list of names** (`SCHEDULE_FACTS`, `NOTE_FACTS`, `LABEL_FACTS` in `adapters.py`),
  used only to label the kind of evidence and the family. The plan says such lists belong in YAML; moving them is small and not done.
* **Matching by meaning is word overlap, not understanding.** It handles "door_clear_width" for `width_m`. It does not handle
  synonyms or other languages; that is for a producer that holds a word list or an embedding.
* **A fact the graph marks as conflicting** has no value, so it enters the ledger as "read, no value", not as a conflict.
  Today no producer writes one.
* **Tolerance of 0.5 percent** decides that two numbers agree. Two readings of one door at 0.900 and 0.903 m agree; 0.90 and 0.91
  conflict. That is a choice, written on the request so a rule can set its own.

## Wiring still needed (I did not touch these files)

1. `interpreter/checked.py`: where the inputs for a run are built from the fact graph, replace `to_inputs(fg)` with
   `ledger_inputs(fg, attestations)` (same result, as measured) or `inputs_for_program(program, fg, ledger)` per rule. Keep one
   `Ledger` for the whole review so a reviewer's attestation applies to every clause that asks the same question.
2. `interpreter/findings.py`: for a NOT_EVALUATED finding, list `resolution.explain()` of the unresolved ones and offer
   `resolution.followup()` as the question to the reviewer. For a conflict the message should name both sources.
3. Reviewer answers: write them with `Attestations.attest(...)` (name and source mandatory) and persist them next to the project,
   so a reload restores them.
4. When `origin/rule-interpreter` is merged: map `Candidate.kind` to her `origin` with `ORIGIN_OF_KIND`, fill `Fact.origin` and
   `Fact.reviewer` in `Resolution.fact()`, and let `apply_evidence` and the ledger share one entry list. `requests_for_program` is the
   natural replacement of hand written `FactDeclaration` lists for facts the catalogue already declares; facts it does not declare
   still need her declaration path.
5. New producers (steps 3 to 6) implement `holds` and `answer` and are added to the `Ledger` list; nothing else changes.
