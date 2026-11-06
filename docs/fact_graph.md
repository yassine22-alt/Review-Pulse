# The facts graph

The facts layer turns a plan into a graph that the rule judge reads. It is one JSON file per building. The format does
not know what kind of building it describes: the kinds of things, the names of their attributes, and what those
attributes mean and measure in are all declared inside the file. So a plan reader, a schedule reader, or a person can
each add facts in the same format.

Schema: `schemas/factgraph.schema.json`. Code: `src/reviewpulse/factgraph/`.

## What is in the file

| Part | Meaning |
|---|---|
| `nodes` | The things on the plan: rooms, doors, windows, stairs, the building as a whole, the outside. Each has a kind, a role (member, whole or boundary), an optional label, and attributes |
| attributes | Each value carries its `source` (which sheet and element it came from) and a `trusted` flag. A value that could not be measured is absent or untrusted |
| `edges` | Relations between nodes: through a door, through an opening, adjacent. Each says whether it is established or only plausible |
| `bindings` | The meaning, type and unit of each attribute name used in the file |
| `inventory` | For each kind, whether the list is complete (every member listed) and trusted (a listed member really exists) |
| `value_labels` | The words documents use for each value (for example the many names of a bedroom, in several languages), used to match requirement text to plan values |
| `provenance` | The document and sheet, the quality tier of the reading, and how the scale was fixed |

## The rule that matters most

An unknown value is never a pass. If a value is missing or untrusted, a rule that needs it is unresolved. If the list of
things of some kind is not marked complete, a rule over every member of that kind is also unresolved: "no stairs were
found" does not mean "there are no stairs". The stair finder reaches about half of the stairs that are drawn, so the
stair list is never marked complete.

## Reading and writing it

```
python -m reviewpulse.factgraph export <building.json> <out.json>   # from the plan reader's building model
python -m reviewpulse.factgraph show <out.json>                      # a short readable summary
python -m reviewpulse.factgraph schema <out.json>                        # write the JSON schema
```

In code: `factgraph.from_building.from_building(model)` produces the graph, `factgraph.io.dump / load` write and read it,
and `factgraph.convert.to_catalogue / to_inputs / to_graph` give the rule interpreter what it needs: the declared
collections and facts for drafting, and the values for judging.

## Trust, in short

- Room and opening measurements are trusted when the plan reading is at the highest tier (T1) and the scale is known.
- A room type read by a language model is not trusted.
- A stair measurement is trusted only when the fit is tight, the chance of a false flight is very small, and the
  calibrated probability that the flight is real is at least 0.8 (see `docs/progress/M7_rule_extraction_facts_and_stairs.md`).
