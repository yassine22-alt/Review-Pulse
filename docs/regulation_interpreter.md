# Compound regulation interpreter

The `rule-interpreter` branch adds a separate, opt-in interpretation workflow to the existing application. It reuses the LLM clients, clause splitter, BuildingModel and room-graph builder. Existing starter packs, their checks, their verdicts and the current Rules tab retain their existing behavior.

## Run an offline demonstration

From the repository root after its normal installation:

```powershell
rp interpret demo runs/interpreter-demo
rp interpret check runs/interpreter-demo/exit_capacity/program.json runs/interpreter-demo/exit_capacity/inputs.json runs/interpreter-demo/result.json --preview
```

The demo writes three programs, their contexts, input facts and twelve independently specified scenario outcomes: cumulative inner-room conditions with alternative warning arrangements, capacity after excluding a largest contribution, and a dining-area exception with a strict area-ratio boundary. They are illustrative subsets, not complete or authoritative encodings of Approved Document B or ADA requirements. Source contexts identify them as fixtures.

## Interpret a document

```powershell
rp interpret context requirements.md "Art. 9" context.json
rp interpret inputs runs/plan/building_0.json inputs.json
rp interpret draft context.json inputs.json draft.json
rp interpret check draft.json inputs.json preview.json --preview --building runs/plan/building_0.json
rp interpret review draft.json context.json inputs.json review.json
rp interpret approve draft.json context.json inputs.json review.json approved.json "Reviewer name"
rp interpret check approved.json inputs.json result.json --building runs/plan/building_0.json
```

Draft and review use Ollama by default; both accept the existing `--backend` and `--model` options. Each is one bounded model call, with no automatic retries or repair. Review is a separate prompt/model role; it is not a correctness proof. Inspect the interpretation and independent cases before explicitly approving it. Model output is always reset to draft and cannot remove unresolved context dependencies. Editing a program, source context or capability meaning invalidates its review fingerprint.

The exported input file is also the capability catalogue. Extend its declared bindings and source-linked facts for information from schedules, specifications or human review. A declaration supplies a type, unit and description; a fact supplies its value, source, trusted flag and conflict flag. No missing physical concept is silently replaced with an available measurement. Derived/table-selected input facts need their own verified provenance; automatic table semantics are not implemented here.

## Document context

The existing splitter supplies clauses and offsets. Context assembly follows subitem parents/children and explicit numbered paragraph/article/section/table references, with a cycle guard and a 40-clause budget. Missing, ambiguous or budget-truncated references remain unresolved. Definitions and references that are not explicitly numbered can be supplied in a JSON link map via `context ... --links links.json`.

This does not yet reconstruct an arbitrary PDF's full heading/definition/table hierarchy or resolve external standards automatically. Source quotes are checked against exact document offsets. Anchors establish traceability, not semantic completeness; a model can still omit meaning and requires independent review and evaluation.

## Expression semantics

Expressions are a closed discriminated union. Unsupported nodes and extra fields are rejected. Supported operators are `all`, `any`, `not`; equality/inequality comparisons; unit-checked arithmetic; `forall`, `exists`, `count`, `sum`, `min`, `max` over named collections; and `path_exists` with room/edge predicates. Variables are explicitly bound. Shadowed and unbound variables are rejected. Runtime work is bounded.

Use `applicability` for the rule's scope, `exemption` for an exemption from the obligation, and `requirement.any` for alternative compliance. Do not treat permission as an obligation. Full defeasible rule priorities, obligations over time, normative conflicts between rules and arbitrary recursive definitions are not implemented in this version. Conflicting input facts become unknown, not an automatically resolved legal conflict.

Units are `1` (dimensionless), `m`, `m2`, and `count`. Compatible addition/subtraction, multiplication by a dimensionless factor, length squared, equal-unit ratios, and area divided by length are supported. Other dimensional operations are rejected. There is no implicit tolerance or numeric rounding; supply the correct source comparison and quantities. Zero division, empty min/max and non-finite arithmetic return unresolved results.

Unknown, untrusted or conflicting facts never become false. A known true disjunct can satisfy an alternative despite an unknown sibling. A known false conjunct can establish a violation. Missing facts in irrelevant branches remain visible as diagnostic trace entries even when the final outcome is decided.

Collection members must be explicitly trusted. `complete` separately declares whether additional members may be missing. Universal satisfaction and existential failure require complete inventories; a witnessed universal failure or existential success does not. Aggregates conservatively require complete membership and known qualifying values; lower-bound interval reasoning is not implemented. A universal over an entirely empty collection is unresolved, deliberately avoiding a silent certification of an empty extracted scope.

`path_exists` checks one coherent route: every accepted room and connection on it must satisfy its filters. It searches a known graph and a possible graph rather than enumerating all simple paths. Graph completeness is required to prove no qualifying route exists. It reuses `engine.context.build_graph`; it does not measure travel distance or assert multi-floor completeness. `$node` and `$edge` are reserved filter variables, with `$edge` bound to the opening element id. EXIT/EXTERIOR sentinel nodes are not tested as rooms. Evidence is the tree of consulted facts and connection diagnostics; minimal witness extraction is not yet implemented.

## Building evidence

`interpret inputs` reads a saved building without segmentation. T1 measurements additionally require a recognized scale method; LLM/VLM-derived labels remain untrusted. Opening measurements on lower tiers require element confirmation and a recognized scale. Room measurements below T1 remain conservative. Connections use T1 or confirmed opening evidence.

Inventories default to incomplete. `--complete` is an explicit declaration that the exported inventory has been reviewed as complete; it also attests member identity, but does not certify unknown measurements or labels. `inputs.graph_complete` controls negative path claims. Review this declaration against the actual drawing scope. There is no automatic whole-building or cross-floor assembly.

## Application API

The existing FastAPI app registers stateless endpoints under `/api/interpreter`: `context`, `draft`, `review`, `approve`, and `check`. They expose the same functions and approval policy as the CLI and appear in `/docs`. Check optionally accepts the saved BuildingModel for graph evaluation. These endpoints do not accept filesystem paths. Drafting fails explicitly when the configured model is unavailable.

Compound programs and their richer outcomes are not yet persisted in the project's legacy draft queue, displayed in its Rules tab or merged into PDF/HTML finding exports. Keep them separate until those interfaces can faithfully represent applicability, exemptions and unresolved interpretation. The current endpoints and CLI allow end-to-end interpreter development independently of that UI migration.

## Verification

Run `pytest tests/unit/test_interpreter.py tests/app/test_interpreter_api.py` and the existing drafting/engine regressions. Tests cover branch semantics, strict ratio boundaries, post-exclusion aggregation, incomplete/untrusted collections, unknown filters, graph conjunctions, units, variable scope, invalid code nodes, quote validation, context cycles, stale review, approval, CLI output and HTTP workflow. Model transport uses offline stubs; these tests do not measure a real LLM's interpretation accuracy.

Next research work: expert-reviewed full-source requirement groups, measured model accuracy/cost, context reconstruction for difficult PDFs, structure-aware example retrieval, bounded interpretation repair, generated distinguishing scenarios and legacy review/report integration. None is implied by passing the deterministic tests.
