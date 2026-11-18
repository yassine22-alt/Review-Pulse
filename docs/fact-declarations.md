# Source-grounded fact declarations

A declaration supplies a name and a type, never a measured value. Structured
drafting may propose a name, numeric/boolean/string kind, unit, known entity
or collection, definition and exact source quotation. No clause identifiers,
room categories or numeric examples are embedded in this mechanism.

The compiler grounds the quotation, checks the unit vocabulary and type,
checks entity ownership, and rejects replacement of existing bindings,
unused declarations and unsupported entities. The normal quantity/cue
verifier and expression round trip still apply. A declaration is not proof
that its definition correctly interprets the source: human approval remains
necessary. No new entity inventory or plan computation is created.

Retained IR that needs a declared value is labelled `NEEDS_EVIDENCE`, with
outcome `UNRESOLVED`. Applying declarations creates missing ledger slots with
no value and no extracted/computed provenance. Only named reviewer-attested
evidence with a source citation may fill those slots. Conflicting or
untrusted evidence remains unresolved. Findings retain declaration metadata,
attestation provenance and evidence requests. Inventory completeness is
unchanged. For this initial policy, a missing declared fact actually read by
a rule prevents both satisfied and violated decisions, even when another
conjunct is already false. Non-applicability and exemption remain separate.

Unit aliases, including `W/m²/K` and `m²·K/W`, live in `units.yaml`; generation
choices are built at runtime from that data and the catalogue. Dimensional
compatibility is checked independently of spelling.

## Development oracle

All 46 gold slot frames are development data, authored without independent
review. This run does not call a model. The historical comparison that adds
author-proposed facts and missing collections directly is a permissive oracle,
not the production declaration mechanism.

| Mode | Retained / 46 | Exact frozen trees / retained | Generated behavior matches / retained |
| --- | --- | --- | --- |
| Active catalogue | 5/46 | 5/5 | 5/5 |
| Author-supplied catalogue expansion | 17/46 | 17/17 | 17/17 |
| Validated declarations, existing entities only | 13/46 | 13/13 | 13/13 |

The validated mode rejects 33/46: verifier 23/46, entity binding 8/46,
missing context 2/46, unit vocabulary 0/46. Per-case diagnostics and the number
of declarations are in `reports/slot-oracle-declarations.json`. The four-case
gap from the permissive oracle reflects the refusal to create missing entity
collections, not a hidden computation implementation.

All five selected thermal pilot gold frames are among those verifier rejections
(5/5): source-number coverage demands the table's 26–35% applicability bounds,
while the frozen frames assume that scope externally. This is a scope-contract
mismatch between the oracle and validator, not evidence of weak model capacity.
No frozen label or coverage check was changed. A model could instead draft
explicit applicability, which still needs grading against the frozen scope.

Each behavioral comparison uses 64 synthetic complete-value worlds. It strips
declaration provenance solely to compare compiled logic; it does not count
those invented values as real ledger evidence. Matching evaluation errors
are never credited as behavioral agreement. Separate runtime tests verify
missing values, reviewer evidence, conflict, type errors and incomplete
inventories. These numbers establish neither model accuracy nor real-plan
coverage. Benchmark attestations remain synthetic. The fourth document is
unrun.
