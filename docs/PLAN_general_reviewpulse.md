# The plan for a general ReviewPulse

Written 25 November 2026, after M15. This page is for anyone joining the project. It says where ReviewPulse is, what it must be
able to do, what stands between the two, and how we close that gap step by step with the strongest method we could find for each
part. We work through it in order; every step ends with a measurement and a progress note in `docs/progress/`, and the step only
counts as done when its measure says so.

The rule for every step: the most general method that fits, found in the literature and tested against a stronger alternative on
a measure that needs no labels. No patch for one document, one word list or one building type. Every loss is written down.

## 1. Where we are

Measured numbers, from `docs/SCOPE.md` and the M12 to M15 notes.

| Layer | What works | What does not |
| --- | --- | --- |
| Reading requirement documents | Any file type, scans included (recall 1.00 on synthetic scans), tables named by caption (165 of 168 UK table references resolve), 32 format variants at recall and precision 0.99 | References to other sections, definitions and exceptions elsewhere in the document are not followed; only tables are |
| Reading drawings | Clean vector plans: walls, doors, windows, rooms, scale, routes. 13 generated variants pass, planted errors 3 of 3 | Each sheet is read alone. There is no model of the set: views, view scales, callouts, sections, details, legends, levels. Real complex sheets are "readable with caveats" at best |
| Facts | A fixed list: room sizes, door widths, connections, distances, stairs where found, note counts for nine kinds, door fire rating from the schedule | Everything else. Of the 56 labelled checklist lines a plan can speak to, 46 need a fact we do not have |
| Evidence | For a declined clause, the note of the set that is about it: 17 of 46 lines on a real permit set (14 right, 3 partial, 0 wrong) | Text layer only: outlines, scans and symbols give nothing. The note is quoted, never turned into a value a rule can use |
| Rules | Limits on one measured quantity and connection rules, checked by programs and multiple choice questions. 8 of 10 decidable lines correct, 0 wrong | Conditions, exceptions, alternatives and several limits in one sentence are declined |
| Decisions | Three valued: unknown is never a pass | No calibrated confidence; no "missing information" verdict that asks the one question that would unlock a clause |
| Measurement | Label free audits, planted errors, planted notes, three real drawing sets | Labels by one AI grader, not checked by a person; the hosted model has never run on this code |

**The bottom line.** On the labelled lines of four real checklists, ReviewPulse decides 8 of the 56 lines a plan can speak to,
without a wrong decision, and quotes evidence for 17 more. Everything else is declined honestly. The bottleneck is not reading
the requirement any more; it is the facts.

### What ykram051 built on `origin/rule-interpreter`, and what we take

87 commits, 17 to 19 November, read on 25 November; nothing new has been pushed since. Her conclusion is that the product is "an
assisted numeric drafter and expert formalization workspace, not a general interpreter". That conclusion is the opposite of our
goal, so her scope gate and her closed menu of fact names are **not** adopted as the boundary of what ReviewPulse can check. Several
of her pieces are exactly what the general design needs, and we take them, merged with care into `checked.py`:

| Her piece | Why it fits | How it is used here |
| --- | --- | --- |
| `interpreter/evidence.py`: `EvidenceEntry`, `EvidenceRequest`, `apply_evidence` (conflicting values stay conflicting, a source is required) | It is the evidence ledger the plan needs | The ledger becomes the single place where every producer of facts (section 4) writes, not only reviewers |
| `FactDeclaration` and `declarations.py` (a name and a type, never a value) | A requirement can ask for a fact that no list holds | The declaration becomes a **fact request** that is sent to producers first and to the reviewer last |
| `metadata_applicability` (applicability kept apart from the requirement, typed conditions with a source span) | Conditional requirements need exactly this | Project facts are read from the drawing set (step 4) instead of being typed by hand |
| Structured drafting with a compiler and a slot round trip, schema passed to Ollama and Gemini | Stronger checks on what a model writes | Kept as the drafting path for the new normative form (step 5) |
| Resilient hosted runner, result cache, Gemini client | We have never run the hosted model on our code | Used for the ceiling run (step 0) |
| Preregistered criteria, frozen holdouts, blinded grading, "do not claim" lists | Trust discipline | Adopted for every measure in this plan |
| Scope gate, closed fact menu, assisted only product framing | Narrows instead of generalising; queued 6 of 18 in scope clauses | Not adopted. The scope gate may remain as one signal for triage, never as a wall |

## 2. What ReviewPulse must be able to do

Our ambitions, made concrete enough to measure.

1. **Take a real submission as it comes**: a drawing set of many sheets (plans, elevations, sections, details, schedules, notes,
   code analysis, cover), vector or scanned, any language, any drafting style, and a requirement document of any kind.
2. **Understand the set as a whole**: which view is on which sheet, at which scale, which callout points to which detail, which
   legend explains which symbol, which plan is which level, and what the project is (use, size, number of storeys, sprinklered or
   not, code edition) as the set itself states it.
3. **Turn each requirement into its real logical form**: who it applies to, under which conditions, what it requires, its exceptions
   and alternatives, each part tied to the words of the source.
4. **Find any fact a requirement asks for**, wherever the set holds it: measured from geometry, read from a schedule, a dimension
   string, a note, a symbol with its legend, a detail, or the code analysis sheet. Each fact has its source and a confidence.
5. **Decide as much as the evidence honestly allows**: meets, does not meet, missing information (with the one question that would
   settle it), or uncertain, with a controlled rate of wrong decisions.
6. **Be a reviewer's assistant**: every finding is shown on the sheet with its quote; one answer from the reviewer unlocks every
   clause that depends on it; nothing is approved without a person.

## 3. The gap, and its root cause

| Ambition | Today | Root cause |
| --- | --- | --- |
| 1, 2 Understand the whole set | One sheet at a time; general notes found over the set, nothing else | No model of the drawing set as a document: views, references, legends and levels do not exist as objects |
| 3 Logical form | One limit or one relation per sentence | The rule language has no applicability, exception or alternative structure, and documents are not read as a graph of references |
| 4 Any fact | A fixed list, produced before any requirement is read | **Facts are produced bottom up into a closed schema.** A requirement can only use what perception decided in advance to produce |
| 5 Decide | 8 of 56 | Follows from 4, and there is no calibrated way to accept a fact read by a model |
| 6 Assistant | Notes and warnings per clause | No question queue; no evidence crop on the sheet; the ledger is not wired to the review screen |

The central change is therefore the third row. **ReviewPulse moves from bottom up fact production to demand driven fact
production**: each requirement states the facts it needs as typed requests; every producer that might hold that fact (geometry,
schedules, dimensions, notes, symbols, project data, a vision model) answers with a sourced candidate; the ledger fuses the
candidates; the rule runs on what survives, and asks a person only for what nothing could answer. This is the general form of what
M14 and M15 did for notes, and of what ykram051's declarations did by hand.

## 4. The target architecture

```
 requirement document                      drawing set (all sheets)
        |                                          |
  [A] regulation graph                       [B] drawing set model
  clauses, tables, definitions,              sheets > views (kind, scale, frame, level)
  references, exceptions                     callouts and references, legends, title blocks,
        |                                    schedules, notes, project data sheet
  [C] normative form                               |
  applicability / requirement /              [D] producers (each answers fact requests)
  exceptions / alternatives,                  geometry . schedules . dimensions . notes .
  each node tied to source words              symbols by legend . project data . vision model
        |                                          |
        +------> fact requests ----------->  [E] evidence ledger
                                              candidates with source, kind, confidence;
                                              agreement and conflict; reviewer attestation
                                                   |
                                             [F] decision
                                              four states, risk controlled acceptance,
                                              the question that unlocks most clauses
                                                   |
                                             [G] review screen
                                              finding on the sheet, quote, attest, approve
```

Everything is data driven: kinds of views, kinds of facts, units, words in other languages live in YAML files, never in code.

## 5. The steps

Each step lists: the method and why it is the most general one; the literature it rests on; the stronger alternative we test it
against; the label free measure; what counts as done; the risks; and when we stop and change course. Steps 1 to 4 are the spine and
come in this order because each needs the one before. Steps 5 to 8 can partly run in parallel once 3 exists.

### Step 0. Foundation: commit, merge, ceiling

* Commit M14 and M15.
* Merge `origin/rule-interpreter` into our line: her ledger, declarations, metadata applicability, structured drafting, hosted
  runner. The scope gate stays as an advisory signal. The seven files with small conflicts are merged by hand, `checked.py` last.
  Full suite, ruff and self check must pass after the merge.
* **Hosted ceiling run**, never done on our code: the checklist benchmark and the evidence evaluation with a hosted model (keys in
  `.env`, drawings sent only with consent; requirement text only by default). This tells us how much of the remaining gap is the
  7B model and how much is missing facts. It decides how hard we push on the model side in step 5.
* Done when: the merged branch passes, and the ceiling numbers are recorded next to the local ones.

### Step 1. The drawing set model [B]

The substrate for everything after. AEC-Bench (Nomic, 2026) reports that finding the right sheet is the hard part for agents on
real sets, and DrawingVQA (CVPR 2026) reports that models fail at callouts and cross sheet references. We build that structure
explicitly instead of hoping a model infers it.

* **Views**: each sheet is cut into views (a plan, an elevation, a section, a detail, a schedule, a legend, a notes block, the
  title block). Method: layout regions from the vector drawing (enclosing frames, whitespace gaps, view title bars with a scale line
  under them, as in "FLOOR PLAN 1/4" = 1'-0"" or "GRUNDRISS EG M 1:100"), classified by a learned layout model where the text layer
  is missing. Each view gets its own scale, unit and coordinate frame: one sheet often holds views at several scales, which today we
  get wrong silently.
* **References**: callout grammars (detail number over sheet number, section marks, "SEE 3/A-501", "voir détail 4") parsed from the
  text layer and from OCR, resolved to the target view. Same idea as the table references of M14, which went from 0 to 165 of 168.
* **Sheet index and title blocks**: the index on the cover against the title block of each sheet.
* **Legends**: each legend entry stored as an exemplar (the drawn symbol plus its words) for step 6.
* **Levels**: each plan view assigned to a level (title words, elevation marks, stairs that appear on two plans), so routes can
  later cross levels.
* Literature: AEC-Bench (cross reference resolution, cross reference tracing, sheet index consistency, drawing navigation);
  DrawingVQA; Blueprint (2026, region detection then region restricted OCR on title blocks and revision tables); SALI-FP (2026,
  evidence gated parsing: a step may only revise what its evidence authorises).
* Stronger alternative to test against: a vision model (Qwen3-VL class) asked to list views and references per sheet. We keep the
  structural parser if it wins or ties, and use the model only where the text layer is absent.
* Measures, no labels needed: share of callouts that resolve to an existing view on our real sets (as `table_refs.py` does for
  tables); sheet index against title blocks; metamorphic checks (rotate a sheet, rename a sheet, move a view: the references must
  follow). External: the AEC-Bench intra drawing tasks, which ship expert answers and are Apache 2.0, run locally on the subset our
  hardware allows.
* Done when: callouts resolve on the US permit set and the Florida set at a rate we report with every unresolved case read, and each
  view carries its own scale.
* Risks: scanned sets with no text layer; a hand drawn set. Stop rule: if layout detection on scans is below what the vision model
  gives, the model becomes the scan path.

### Step 2. Fact requests and the evidence ledger [E]

The spine of the new design.

* A **fact request** is a typed question: the entity (a kind of space, element or the whole project), the property, its kind
  (number with dimension, yes or no, category), its unit, and the words of the clause it comes from. It is ykram051's
  `FactDeclaration`, extended with the dimension from our unit table, and created by the normative form (step 5) or by today's
  drafting arms.
* A **producer** is anything that can answer a request: the existing geometry, the schedule reader, notes, and the new producers of
  steps 3, 4 and 6. Each declares what it can answer (kinds of entity and property, by meaning, not by a fixed name) and returns
  candidates: value, unit, entity it binds to, source (sheet, view, region, words), the kind of evidence (measured, stated,
  inferred, attested) and a score.
* The **ledger** (her `apply_evidence`, extended) fuses candidates: agreement between independent producers raises trust, a
  conflict stays a conflict and is shown with both sources, and a reviewer's attestation outranks everything.
* Binding a request to entities uses the fact graph we have, with names matched by meaning across languages (bge-m3 plus the
  cross encoder of M15), so "Treppenlauf", "stair flight" and "escalier" reach the same kind.
* Literature: evidence grounded constraint checking (Cocoon Lab, 2026: typed facts, deterministic four state rules, source spans,
  fail closed escalation); the LLM BIM compliance study (Automation in Construction, 2026), whose stated weakness is that missing
  data became "non compliant" instead of "insufficient information", and whose proposed fix is that the rule agent requests missing
  facts. That is this step.
* Stronger alternative: one model call that reads the clause and all candidate passages and writes the answer. We compare it to the
  ledger on the same clauses; the ledger must be at least as right and always traceable.
* Measure: on the 56 plan lines, how many requests are created, how many find at least one candidate, how many are answered with
  agreement, and how many wrong values the ledger accepts (planted value swaps in schedules and notes must all surface as
  conflicts).
* Done when: every existing fact goes through the ledger with no change to the benchmark (8 of 10, 0 wrong), and planted swaps
  surface.

### Step 3. Producers that read what the set states [D]

Each producer is general by construction: it reads a kind of drawing evidence, not a kind of requirement.

* **Schedules and tables on sheets, any columns.** Today we read the door schedule's fire rating column by name. Instead, every
  table on every sheet becomes rows of an entity kind (doors, windows, rooms, fixtures, finishes) with each column typed by its
  header's meaning and unit, using the table reader of M13 and M14 and ykram051's `table_rows.py` (column units, typed scope).
  Rows bind to drawn elements by their tags ("D-12", "W3").
* **Dimension strings.** A dimension's value bound to what it measures, using the geometry of the dimension line, its extension
  lines and its leader, not the vision model (2026 work on engineering drawings finds that models read the numbers well, F1 0.96,
  but are unreliable on leader geometry and association). Our existing dimension reader gives the strings; this producer binds them
  to walls, openings, stairs and rooms, and checks them against measured geometry.
* **Notes with values.** M15 finds the note; this producer extracts its value and unit with the unit table and binds it to the
  request, with the figure check of M15 (planted contradictions must say "contradicts").
* **Details through callouts.** A request about a guard height or a stair riser follows the callout from the plan to its section
  or detail (step 1) and reads the dimension there.
* Stronger alternative for each: the vision model reading the same region. We keep the deterministic producer where it matches or
  beats the model; where the model is better, it becomes a producer too, gated by step 7.
* Measure: on the real sets, facts answered per producer, agreement between producers when two answer the same request, and
  metamorphic checks (change a schedule value, the answer must change; change the unit, the value must convert).
* Done when: on the US permit set the requests about fire ratings, glazing, stair geometry, window sizes and ceiling heights are
  answered from schedules, dimensions or notes with sources, and the "20 minute garage door" figure comparison lost in M15 is back.

### Step 4. Project facts and applicability from the set itself

Many requirements apply only in some cases ("townhouses require sprinklers", "stairs with four or more risers"). About 9 of 20
mention rules in M14 were conditional. Decisions need the conditions.

* Project facts are what a code analysis sheet or cover states: use and occupancy, construction type, number of storeys, floor
  area by level and use, sprinklered or not, the code edition and jurisdiction. A producer reads them from the cover, the code
  analysis block and the title block, as typed facts with a source, using ykram051's `metadata.yaml` for the kinds of fields
  (extended, data driven).
* Conditions about the building itself (four or more risers, a dwelling unit above another) are computed from the fact graph.
* What the set does not state stays unknown and becomes a question (step 8). Nothing is guessed from the drawing's look.
* Measure: on the real sets, project fields found with a source; on the checklist, conditional lines whose condition becomes known.
* Done when: conditional lines carry a known or explicitly unknown condition instead of being declined.

### Step 5. The normative form and the regulation graph [A, C]

* **Regulation graph.** Sections, definitions, tables and exceptions become nodes; "except as provided in 1011.5", "as defined in
  Section 2", "see Table B4" become edges, resolved deterministically before any model reads the clause. RegulaRAG, GraphCompliance
  and ComplianceNLP (2026) all find that deterministic traversal of references and exception chains, then the model on the resolved
  context, beats retrieval alone (graph reranking gave the largest gain in ComplianceNLP, +4.6 F1).
* **Normative form.** A clause is first cut into atomic obligations (the defeasible deontic logic pipelines of Governatori and
  colleagues, 2025 and 2026), then each obligation is written as a tree tied to the source words: applicability, the requirement,
  exceptions (defeaters), alternatives, and the facts it needs. This is the span grounded deontic tree of NormBench (KDD 2026), which
  showed that models silently drop nested exceptions and that a constrained intermediate form with explicit exclusion guards fixes
  it. It compiles to our existing expression language, extended with an explicit `unless` and with applicability kept apart (her
  `metadata_applicability`).
* **Faithfulness without labels.** Round trip verification with a formal equivalence check (Faithful Autoformalization via
  Roundtrip Verification and Repair, EMNLP 2026 Findings): formalize, write back to words, formalize again, and check that the two
  trees are equivalent, by enumerating fact worlds (her 64 world check) or with an SMT solver (z3) for numeric limits. A mismatch
  points at the node to repair. Our current round trip (`interpreter/roundtrip.py`) compares words; this makes it logical.
* **Models.** The 7B model is a chooser, not a writer (M11, M15). The hosted model drafts when consent is given; locally the tree is
  built by choosing among enumerated options per node (which quantity, which direction, which condition), with position balanced
  voting. Constrained decoding is applied after the model has reasoned, not during: the 2026 "constraint tax" study measured that
  hard schema decoding lowered a small model's accuracy from 19.7% to 11.0% while raising validity to 100%.
* Stronger alternative: agentic program synthesis of a checker in Python (ARCHER, NeurIPS 2026 workshop). It needs labelled train
  models per rule, which we do not have and will not ask for, and a program is harder for a reviewer to read than a tree, so it is
  the comparison, not the design.
* Measures: the checklist benchmark per line, with exceptions and conditions now counted; round trip equivalence rate; the planted
  rule perturbations of M11 (swapped direction, dropped exception) must all be rejected.
* Done when: compound, conditional and excepted lines are written as trees that pass equivalence, with no new wrong rule.

### Step 6. Seeing what is drawn, not written [D]

What words alone cannot reach: symbols with no word beside them, notes drawn as outlines, scanned sets.

* **Vision model upgrade.** Replace `qwen2.5vl:7b` with a Qwen3-VL class model that runs locally (the 8B is reported at about 6 GB
  quantised; we verify on this laptop before adopting). It reads regions and points at what it names, so every reading has a place
  on the sheet.
* **Visual retrieval over tiles.** Each sheet is cut into overlapping tiles and indexed. Two methods are compared on our planted
  notes test (rendered as outlines and as scans) and on the real sets: late interaction visual retrieval (ColQwen2.5 or ColNomic-3B:
  91% recall@5 on a 4 056 pair benchmark of civil standard plans in PlanSightRAG, 2026, with no OCR), against index time
  enrichment (MIDR, EMNLP 2026: a vision model writes verified text fields for each tile once, then words and meaning retrieval as in
  M15; competitive with ColQwen2.5 at about nine times less memory, and it bridged English queries to French pages). On a laptop the
  second is likely the better fit; the measurement decides.
* **Symbols by their legend.** Each legend entry (step 1) is an exemplar; symbols in the plan are matched to it by a learned
  embedding (legend informed contrastive matching, ECML PKDD 2025, over 80% accuracy across drawing styles with no labels, and able
  to say "not in the legend"). One shot in context querying of a vision model is the alternative (BlueprintSymVL, 2025).
* Measure: planted symbols and outline notes in generated sets (truth by construction); on real sets, symbol counts against the
  counts the notes or schedules state, which is a free cross check.
* Done when: smoke alarms, exhaust fans and similar symbols are counted per room on a real set with a legend, and outline notes
  are retrieved as well as text notes.
* Risks: memory (6 GB GPU shared with the text model; run the vision work at index time, one model at a time); speed on scans.

### Step 7. Learned geometry as a second opinion [D]

Our geometric reader is precise on clean CAD and weak on complex real sheets; ykram051 measured poor transfer of the learned models
we have on real PDFs (0 of 4 bedrooms classified on a real sheet).

* Add a pretrained panoptic symbol spotter on vector primitives as an independent producer: VecFormer (NeurIPS 2025, PQ 88.4 on
  FloorPlanCAD, and far better on walls and other "stuff" classes, 85.9 against 49.3) or SymPoint-V2, whichever has usable weights.
  For raster sets, a floor plan vision model trained for vectorisation (FloorplanVLM, 2026, Qwen2.5-VL with reinforcement learning,
  92.5% external wall IoU on its own benchmark; independent results not yet published).
* Its output is never trusted alone: where it agrees with our geometry, trust rises; where it disagrees, the fact is marked and the
  reviewer sees both. Agreement between independent methods is the label free signal.
* Measure: room and opening agreement on our real sets, the ResPlan stress test of M11, and ArchCAD or FloorPlanCAD held out sheets.
* Stop rule: if real sheet agreement does not rise above what we have, the learned model stays out and we record why.

### Step 8. Decisions with a controlled error rate, and the question queue [F, G]

* **Four states**: meets, does not meet, missing information, uncertain (as in evidence grounded constraint checking, 2026). Today
  "cannot be determined" mixes the last two; a reviewer needs to know whether to ask the applicant or to look closer.
* **Risk controlled acceptance.** A fact from a model producer is accepted automatically only above a threshold set by conformal
  risk control, per producer and per kind of evidence (a 2026 study on per field document extraction shows that one global
  threshold silently breaks the guarantee, and that conditioning on grounding restores coverage at held risk). The calibration data
  are the generated sets with truth by construction and the planted perturbations; we state plainly that a real set may differ from
  them, which is the known limit of this guarantee.
* **The question that unlocks most.** Unknown facts are grouped across clauses; the reviewer is asked first the question whose
  answer decides the most clauses ("Is the building sprinklered? 7 clauses depend on it"). The answer is attested into the ledger
  with the reviewer's name and source.
* **The screen**: each finding shows the crop of the sheet where its evidence is, the quote, the clause words, the state, and
  approve or reject. ykram051's timed review workflow is reused to measure reviewer minutes.
* Measure: risk and coverage curves on generated sets; on real sets, decisions made and every wrong one read; then a session with a
  real reviewer.

### Step 9. Levels and routes across them

Plans of several levels joined by stairs and lifts found on two plans (step 1), so that travel distances and routes to an exit are
followed between floors. The general method is already in place (relations by role, `reaches_<boundary>`); what is missing is the
alignment of levels.

## 6. How we measure the whole

* **North star**: of the plan lines of the real checklists, how many are decided (meets or does not meet) with zero wrong, how many
  are "missing information" with the right question, and how many carry cited evidence. Today 8 decided, 17 with evidence, of 56.
  We also report it against new requirement documents and drawing sets not used while building, frozen before the run, as
  ykram051 did.
* **Label free tools** for each layer (reference resolution, metamorphic changes, planted errors with every rule rerun on the
  generated geometry, agreement between independent producers). The "Pitfalls in evaluating automated building plan review" study
  (2026) found that planted defects have side effects the answer key does not name and that its clean cases were not clean; so the
  truth of a generated set is always derived by running every rule on it, never assumed.
* **External benchmarks** where they exist: AEC-Bench (drawing sets, cross references, sheet index), DrawingVQA, FloorPlanCAD and
  ArchCAD for geometry.
* **Planted errors stay all found** after every step.

## 7. Risks we take on purpose

* Demand driven facts (step 2) touch the whole pipeline. We keep the old path running beside it until the benchmark is equal.
* Learned perception (step 7) may not transfer to real sets; agreement gating limits the harm, and the stop rule ends it.
* The hosted model may close more of the gap than the architecture does. Step 0 tells us early; the architecture is still needed,
  because a model without sourced facts cannot be trusted by a reviewer.
* The laptop has one 6 GB graphics card. Vision work runs at index time, one model at a time; anything that does not fit is
  measured once on a hosted model with consent and reported as such.
* Conformal guarantees hold only if real sets resemble the calibration data. We say so and measure the gap on real sets.

## 8. Sources

Building and plan review: ARCHER (arXiv 2607.25566); LLMs for BIM based compliance checking (Automation in Construction, 2026,
doi 10.1016/j.autcon.2025.106707); SGR-BIM graph reasoning (Automation in Construction, 2026); BRAVO benchmark (TUM, 2026);
AEC-Bench (arXiv 2603.29199, github.com/nomic-ai/aec-bench); DrawingVQA (arXiv 2607.15418); Evidence grounded constraint checking
in construction documents (arXiv 2607.29058); Pitfalls in evaluating automated building plan review (Movva, 2026); Vienna openBIM
compliance (Building Research and Information, 2026).

Drawings: VecFormer, line based panoptic symbol spotting (NeurIPS 2025); CADSpotting (arXiv 2412.07377); multimodal symbol spotting
(Automation in Construction, 2026); SALI-FP evidence gated parsing (arXiv 2609.25615); FloorplanVLM (arXiv 2602.06507);
ArchPlanVQA (Journal of Computing in Civil Engineering, 2026: general vision models at 33 to 38% on plan questions); Qwen3-VL
technical report (arXiv 2511.21631); legend informed symbol recognition (ECML PKDD 2025); BlueprintSymVL (Results in Engineering,
2025); dimension extraction with vision models (arXiv 2510.21862, 2602.18296).

Retrieval: PlanSightRAG (arXiv 2608.26091); MIDR (EMNLP 2026); Blueprint multimodal retrieval (arXiv 2602.13345); survey of
multimodal RAG for documents (ACL 2026); RegulaRAG (arXiv 2608.16394); GraphCompliance (arXiv 2510.26309); ComplianceNLP (arXiv
2604.23585).

Formalisation: NormBench and span grounded deontic trees (KDD 2026); defeasible deontic logic with LLMs (arXiv 2506.08899, CEUR
4174); faithful autoformalization via roundtrip verification and repair (EMNLP 2026 Findings); L4L solver centred legal reasoning
(arXiv 2511.21033); GDPR auto formalization with human verification (arXiv 2604.14607); the constraint tax (arXiv 2605.26128).

Uncertainty: conformal risk control for structured LLM outputs (arXiv 2606.29054); per field selective risk control for document
extraction (arXiv 2608.14639); hierarchical group conditional CRC (arXiv 2607.24562); scoping review of conformal prediction for
LLMs (Phil. Trans. R. Soc. A, 2026).

## 9. Real world fit

Added 25 November 2026. Every finding is checked against how plan review really works and who the exact user is. Each line below
is an assumption until a real source confirms it. The sources to use are public plan check correction letters, permit office
submittal checklists and reviewer guides, the real checklists already in `data/real_docs`, and a session with a real reviewer.
When one is refuted, the design changes, not the measure.

**The user.** A plan reviewer at a permit office checking a submission against a checklist or code, or an architect's in house
checker before submission. Their output is a list of correction comments that cite a code section and a sheet, and the applicant
answers them in a resubmission. Their name goes on the review, so nothing may pass without them.

| What we found | The real mechanism we assume | What changes if the assumption is wrong | How we confirm it |
| --- | --- | --- | --- |
| A "-" in a door schedule fire column is now "unknown" (M22) | In real schedules "-" usually means "no rating", not "not looked at". Whether a rating is required depends on where the door is (garage to house, corridor, stair) | Unknown hides a real correction: a door the code requires rated and the schedule shows "-". The finding should say "schedule shows no rating, this door is between X and Y" | Read the legend and notes of the real schedules; read correction letters that cite door ratings |
| Four verdicts: meets, does not meet, missing information, uncertain (step 8) | A reviewer's real outputs are "comply", "correction required" and "information requested". Missing information is a first class outcome that becomes a correction comment | If reviewers do not separate them, the extra state is noise | Count the kinds of comments in real correction letters |
| Findings should be exportable as correction comments (sheet, code section, wording, evidence crop) | The deliverable is the correction letter, not a dashboard | A screen no one can paste into their letter will not be used | Compare our finding text with real comments; ask a reviewer to edit three of ours |
| Real sets rarely state project facts (M20: 2 of 10 gave a use, none gave storeys) | In practice use, occupancy, storeys and sprinklers are on the permit application form or the code analysis, often not in the drawings | An upfront intake form would fit the real flow, but it breaks our rule that the user does not supply a project profile. So we ask on demand, one question that unlocks most clauses, never a profile to fill | Read real submittal checklists to see what the application carries; keep questions on demand |
| Callouts and the sheet index are checked by the drawing set model (M16) | Reviewers do check that references resolve and the index matches, as coordination checks before code checks | If reviewers do not do this, it is secondary work | Read the checklists for "sheet index" and "details referenced" items |
| The checklists we use (Allentown, Berkeley, Bloomfield, St. Petersburg) are residential | The real use includes commercial and other disciplines with different checklists | The facts we prioritise (stairs, egress, fire ratings) may not be the most common comments | Sample real correction letters across building types and count the topics; build the fact priority from that count |
| Reviewers read a note by its location on a sheet | A quote without its place on the sheet is half the evidence | Every finding needs the sheet crop with the note marked (step 8 screen) | Observe a reviewer finding a note on a sheet |

**Next confirmations to do, in order:** (1) collect about thirty public correction letters from several permit offices and count
the kinds of comments, which sets our fact priority and checks the four verdicts; (2) read the legend of the real door schedules
before treating "-" as anything; (3) read two real submittal checklists to see which project facts the application carries;
(4) a review session with a real reviewer as soon as the wired review screen is usable.

## 10. Step 10, the reviewer workflow layer (added after the workflow research)

Research on how review really runs is in `docs/REVIEWER_WORKFLOW.md`. It adds a step that sits across the others, because a
finding that cannot enter the reviewer's real process is not used. The bar for calling any step "working" is a real reviewer
confirming it on a real submission, with the seven measures of section 6 of that page.

* **10a. Run the real public correction lists through ReviewPulse.** The Orange County 2019 list (239 items, 69% with a code
  section, 65 with a numeric limit) and the LADBS sheet are requirement documents in the exact form reviewers hold. Measure how many
  items become a measured rule, a presence check with evidence, or a question.
* **10b. Correction list output.** Numbered, grouped, each item with a code section and the sheet, the evidence crop, and a PDF
  with standard callout annotations that opens in Bluebeam.
* **10c. Reviewer states and routing.** Information requested, deferred submittal and not applicable as states; clauses and
  sheets tagged by discipline.
* **10d. Completeness check** from the drawing set model and project facts against an intake checklist.
* **10e. Back check and applicant response** between two versions of a set.
* **10f. Sessions with at least five real reviewers on ten real submissions**, reporting coverage against the reviewer's own
  corrections, false passes (must be zero), dismissed findings, time, edit burden, fit and trust.

## 11. Measured results since the plan was written

* Steps 1 to 5 (M16 to M21) are built and, with the wiring (M22), the full suite is 1270 passed. None is confirmed by a reviewer.
* **Vision grounding, measured 25 November 2026.** `qwen3-vl:4b` was asked to box each symbol of four real legends of the US
  permit set (43 symbols); the truth is the symbol boxes from the vector drawing. Result: 0 of 43 boxes with overlap of at least
  0.5, mean best overlap 0.09 to 0.21, one legend returned nothing, and the boxes were equal sized steps down the image (a layout
  guess, not looking). It took 4.5 to 8 minutes per legend on this laptop (part of the run shared the machine with the test suite,
  so the time is an upper bound). Decision: the 4b model does not locate symbols and is not used for it. On vector sets the
  symbol boxes already come from geometry, so the model is only needed to choose which legend entry a cropped symbol matches,
  as a chooser among options. Step 6 is reordered: match vector shapes to legend exemplars first, test the model as a chooser on
  crops second, and test the 8b or a hosted model for localisation only for scans.
