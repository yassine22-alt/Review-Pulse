# Checking more obligations with partial evidence

## Diagnostic sample

This is a desk audit of 20 real regulation clauses from the archived
`reports/extractor_eval/real_wording.jsonl` replay. Select every third record
starting at record 1. The archive samples multiple regulations, so it does not
provide the context of a single complete document. All 20 were unresolved in
that historical run: 15 static-stage rejections and five verifier rejections.
The table describes what evidence or interpretation an implementation would need.
It is a design audit, not an independent gold benchmark or a new model run.

| Archive row | Primary blocker | Evidence or capability needed |
|---:|---|---|
| 1 | External evidence | Upstand thermal transmittance from an assembly specification |
| 4 | External evidence | Heating-system type and circuit-control schedule, joined to dwelling scope |
| 7 | Missing computation | Locate controls, establish their elevations, measure clearance from corners |
| 10 | External evidence | Appliance inventory per dwelling, then compare count with floor area |
| 13 | External evidence | Site exposure classification and roof geometry |
| 16 | External evidence | Structural drawings or a wall-tie schedule with spacing and density |
| 19 | Missing computation | Elevations along the access route and seating surface |
| 22 | Missing computation | Route headroom from sections or a 3D model, with doorway exclusion |
| 25 | Interpretation/context | Determine what clearance is required versus merely illustrative |
| 28 | External evidence | Pump power and controls schematic |
| 31 | External evidence | Fixture elevation or manufacturer data and accessible-facility designation |
| 34 | Interpretation/context | Identify the scope of the referenced tread before binding measured depth |
| 37 | External evidence | Insulation thickness and continuity from construction details |
| 40 | External evidence | HVAC capacity and building controls schedule |
| 43 | External evidence | Renovation cost breakdown and relevant scope |
| 46 | Interpretation/context | Recover surrounding ramp conditions, then use slope and rise measurements |
| 49 | Interpretation/context | Decide whether the note creates an obligation and determine its calculation context |
| 52 | Missing computation | Delineate the extension and aggregate its floor area |
| 55 | Missing computation | Barrier geometry for a 3D clearance test |
| 58 | Missing computation | Crawl-space heights and the correct averaging domain |

Primary blocker tally: 10 external evidence, six missing computations, four
interpretation/context. These are engineering judgments from the isolated text.
Several clauses need more than one change, and the largest category contains
different sources. There is no basis for assuming that one adapter clears ten
clauses. The rest of the archive includes a compound exit width/height clause
(row 24), which helped choose an opening-schedule pilot. Its free-height
requirement still needs actual clearance evidence.

## Implemented pilot

The compound evaluator keeps a lower bound of confirmed matching members and
an upper bound of members that might match, when the collection is complete.
With an incomplete collection there is no finite upper bound. A comparison
is decided only when the bounds establish the same truth throughout. This works
in either operand order and inside the existing boolean rules. Count bounds
are included in the evidence trace. Arithmetic over uncertain counts remains
unresolved. A collection marked untrusted cannot supply a confirmed witness.

The plan fact graph now exposes nominal opening height from an existing door or
window schedule. It requires a unique row for the opening's class and normalized
tag and an explicit height unit in the source column with a scalar cell. Only
T1 vector evidence without OCR is trusted. Ambiguous rows and inferred units
are unavailable. The fact is named separately from a measured clear opening
height, with sheet, schedule and tag provenance. The producer adds no special
clause handling. Existing plans without the unit metadata need re-analysis.

## Measuring the next increment

The unit cases contain independent expected outcomes for counts, restricted
routes, and scheduled height. They establish behavior under controlled inputs.
For a coverage claim, freeze separate real documents and annotate applicable
obligations, interpretations, and plan truth before comparing old and new.
Report automatic and reviewer-assisted decisions separately, plus false passes,
precision of violations, unresolved reasons, and the denominator for each
metric. No held-out improvement is established by this pilot.
