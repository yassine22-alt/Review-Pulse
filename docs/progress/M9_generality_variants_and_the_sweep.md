# M9: generality, variant plans and a full sweep of what is left (November 2026)

This page records three things: what we made general (and how we know), the variant plans and tests that show different
parts of the product, and an honest sweep of what is still not general or not good enough, with the reason and the next
step for each.

## 1. Relational requirements, for any subject

A requirement often asks about connections, not measurements: "every room has a door", "a room with one door has a window",
"every space reaches an exit without passing through a bathroom", "no door joins a garage to a bedroom", "the travel
distance to an exit is at most 15 m". Before this milestone only 7 of the 24 clauses of the example document could be
decided on a plan; these were the missing ones.

How it works, and why it is not tied to buildings:

- **Facts derived from any graph.** `factgraph/relations.py` reads the fact graph's own nodes and edges and adds, for every
  member: `links_<kind>` (one per edge kind present), `links_passable`, and `reaches_<boundary>` (one per boundary node).
  For the whole: `links_to_<boundary>`. Trust follows the edges: a count is trusted when every edge it counts is trusted, a
  route that exists is trusted when a route over trusted edges exists, and "no route" is trusted only when the graph is
  declared complete.
- **The producer declares what a route may follow** (`FactGraph.passable`: door and opening for plans, pipe for a network).
  Nothing else in the core knows the word "door".
- **Two operations in the rule language:** `reaches(member, BOUNDARY, avoiding 'a', 'b')` and `linked(a, b)`. The model
  only names categories; code builds the filter from the declared values, and a value nobody declared is refused.
- **A correction in the shared evaluator:** a route filter limits the rooms passed through, never the room the route starts
  from. Without it, "avoid bedrooms" would block the bedroom you start in. The older engine already behaved this way.
- **Geometry stays with the producer.** A travel distance in metres needs the plan's geometry, so the building producer
  computes `exit_distance_m` with the same code the rule engine uses.

How we know it is general: `tests/unit/test_domain_free.py` runs the whole core on a **water network** (tanks, a valve, pipes,
a cable, an outlet) with no building model, no rooms, no doors and no EXIT: clause, checked rule, judge, finding, coverage
report. Another test in the same file uses litres, bar and minutes (section 2).

## 2. Units of any domain

The interpreter allowed four units (1, m, m², count). A hydraulic, structural or thermal requirement needs more, so units are
now dimensional analysis, the model of UCUM and QUDT: a factor to the coherent SI unit and a vector of exponents over the base
dimensions, kept as data in `interpreter/units.yaml`.

- Any unit that parses is accepted (kPa, L/min, kg/m3, mm2, ft, h), with SI prefixes and exponents.
- A value of one unit converts to a compatible unit; a comparison between incompatible quantities (a pressure against a
  length) is refused before anything runs; a length in cm is not silently compared with one in m.
- Products and quotients give a derived unit that parses back (m * m is m2; N / m2 equals Pa).
- Temperatures on an offset scale (degC, degF) convert but cannot be multiplied or divided, as in pint.
- The one-line rule format reads any unit after a number ("500 L", "2 bar", "30 min"), and the sentence check compares the
  number in the sentence with the number in the rule after converting both to SI, so "500 L" in a document matches a rule
  written in m3.
- How documents write units in words is data too: `words:` in `units.yaml` (English, French, German, Spanish, Italian).

Evidence: 17 tests of the unit algebra, and an end-to-end test where a document says "at least 500 L", "at most 2 bar", "no
more than 30 min" and the facts are declared in m3, Pa and s.

## 3. How a document names categories

Documents rarely use a producer's category value. They write "WC" for a bathroom, "living room", "chambre", and they define
groups ("habitable room (bedroom, living room, kitchen)") and use the group's name in later clauses. `xeval/terms.py` maps
those words to declared values using only data: the producer's label table in any language, and the enumerations in the
document's own text. A describing word that is neither a value nor a group ("enclosed") is not a filter, and the drafting
prompt says so. A clause title ("Circulation.") is no longer read as part of the requirement: it named a category and
blocked a correct rule.

## 4. Variant plans: different parts and different ways

`python scripts/make_demo_plans.py` writes 13 plans, each as DXF and PDF with its exact truth, and a README that says what
each shows (see `docs/RUNBOOK.md` for the commands):

clean; one narrow door; small rooms (a rule with two conditions); a bedroom reachable only through the bathroom; a garage
joined to a bedroom; a dead-end room; an exit too far; no exit at all; an isolated room; the same error on a page rotated 90
degrees at another scale; several errors at once; a different drawing style (random layout, French layers, millimetres,
rotated 33 degrees); an L-shaped plan with furniture and hatched walls.

`tests/app/test_scenarios.py` runs every scenario through the whole product (upload, read clauses, approve, check, report)
with a scripted model and compares what the approved rules report with the validated engine's findings on the same plan.
All 13 agree. The French copy of the example document is `docs/requirements_example_fr.md`, and
`scripts/demo_gallery.py` runs the scenarios with the real local model and builds one page that lists them with a link to
each coverage report.

GALLERY_PLACEHOLDER

## 5. The sweep: what is still not general or not good enough

Ordered by the value it would add to a reviewer, with the reason it is not done and the next step.

| # | Gap | Why it matters | Why not done here | Next step |
|---|---|---|---|---|
| 1 | **Ratio requirements** ("at least 40 % of the sum of ..."): none of 6 matched the reference exactly | Ratios are common (glazing to floor area, share of accessible places) | The model writes them as products or mixes sets | Add a typed template to the language, `share(A, B) >= k`, that compiles to a quotient with the denominator rules built in, so the model fills two collections and a number |
| 2 | **The second reader is a 7B model and is noisy**: it raised notes on all 7 rules of the example, several wrong | A noisy critic is ignored, which defeats it | One local model only | Replace most of its work with a deterministic readback comparison (the rule's own plain-words reading against the clause), and keep the model for a second opinion only; or use a larger model where available |
| 3 | **Reading a 24-clause document takes about 15 minutes** | A reviewer will not wait | One 7B model on a 6 GB GPU, about 15 to 40 s per clause | Skip clauses that no producer fact can answer before calling the model; draft in parallel when the hardware allows; offer a hosted model as an option |
| 4 | **Two rule systems** (the older Rules tab and the Requirements tab) | Two places to approve is confusing | The older engine is validated and still carries the drawing-quality checks | Make the Requirements tab the single place: map clauses to the engine's vetted functions (function matching, as in LLM-FuncMapper) with the same sentence checks, so drawing-quality clauses get decided too. The older drafter's mappings were wrong often enough (it dropped the width condition of Art. 6.3) that it must not be merged without the checks |
| 5 | **Languages**: wording and category checks are tested on English and French only; the grounding check runs on English only | The goal is any language | No annotated multilingual regulation text at hand | Collect a small multilingual set of regulation sentences; the wording tables are data, so adding a language is a data task once there is something to test on |
| 6 | **Other producers**: only the building plan reader exists | The format is domain-free, but a new domain needs a producer | Out of scope for this project's data | An IFC and a schedule producer are the natural next ones; the water-network test shows what a producer must provide |
| 7 | **Heights, storeys, occupants and loads** are not read from plans | Many requirements depend on them | They are not on a plan view | A short project form for building-level facts, entered by the user and marked as user-provided in the fact graph |
| 8 | **Perception limits**: stairs 57 % on real drawings, curved stairs missed, text read by OCR can be missed | Each missed element can hide a problem | Needs more labelled data per element type | Keep the honest rule that a list is never declared complete without a person's confirmation |
| 9 | **No usability test with a real reviewer** | The screens were written from what a reviewer needs, not from watching one | Needs a person | One session with someone who is not on the team, recording where they hesitate |

What this sweep rules out: more tuning of thresholds on synthetic data, a bigger prompt, and asking the model to judge
itself. Each was tried or reasoned through and none addresses a gap above.

## 6. Limits of the evidence in this milestone

- The 13 scenario tests use a scripted model: they prove what the code does with a rule once it is written, not how well the
  real model writes it. The real-model numbers are the measurement and the gallery.
- The plans are synthetic. Their truth is exact, and that is why they can be compared with the validated engine, but they
  are not real drawings.
- One shared prompt and one 7B model were used for every number.

## Reproduce

```
pytest tests/unit/test_units.py tests/unit/test_terms.py tests/unit/test_relational.py tests/unit/test_domain_free.py -q
pytest tests/app/test_scenarios.py -q                       # 13 variant plans, scripted model, about 2 minutes
python scripts/make_demo_plans.py demo_plans
python scripts/demo_gallery.py demo_results             # real model, English document
python scripts/demo_gallery.py demo_results_fr --doc fr # the French document
python -u scripts/closed_loop_eval_relational.py 10         # routes, links, door counts, distance: planted errors
```
