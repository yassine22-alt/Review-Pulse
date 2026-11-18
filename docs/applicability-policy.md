# Applicability and requirement

A program has `metadata_applicability` (all typed metadata conditions must
hold) separately from its requirement predicate. Existing fact-dependent
applicability expressions remain supported for compatibility. Metadata names
and types come from `metadata.yaml` and runtime catalogues. New document fields
may be declared by a source-grounded typed condition; they supply no value.

Each condition carries field, kind, operator, value, unit and a grounded source
span. Numbers and string values must be traceable to that span. Numeric bounds
in these conditions contribute to source-number coverage; they do not enter
the requirement expression. Other source numbers still require coverage.

Execution reads only `Inputs.project_metadata`, with value, unit, citation,
trust/conflict status and provenance. Missing, unverified, conflicting, wrongly
typed or dimensionally incompatible values create typed `project_metadata`
requests and an unresolved applicability result. A confirmed false condition
establishes non-applicability. No climate zone or usage is inferred from a
drawing, missing field or table row. Dependencies and metadata provenance are
included in findings. Reviewer attestations require a name and citation.

The first version supports conjunctions of simple metadata comparisons.
Disjunctive or ambiguous scope needs review; do not approximate it with a
conjunction. String equality uses declared values literally; canonical naming
must be reviewed. Source grounding does not prove correct legal interpretation.

## Development oracle

Supplemental thermal scope labels were frozen before this run at
`5537191c37a3b864ba7ca719469991d1a92c5db4`. They are author annotations, without
independent review. The original gold-slot file was not edited. Only the 15
thermal scopes have new annotations; 31 other scopes remain explicitly
unannotated, not assumed unrestricted.

| Mode | Retained / 46 | Verifier / 46 | Entity binding / 46 | Context / 46 |
| --- | --- | --- | --- | --- |
| Before, validated declarations | 13/46 | 23/46 | 8/46 | 2/46 |
| Separate metadata applicability | 28/46 | 8/46 | 8/46 | 2/46 |

All 28/28 retained requirements match their frozen trees and behavior on 64
generated complete-value fact worlds each. These compare the requirement
predicates with metadata stripped; they are not full scope-equivalence tests.
The separate metadata runtime tests exercise missing values, conflicts,
unverified values, incorrect units/types and non-applicability. No model is
called by this oracle. The current targeted suite passes 90/90 tests.

## Rejection taxonomy

Exclusive primary causes for the previous 23/46 verifier rejections:

| Cause | Before | After | Cases |
| --- | --- | --- | --- |
| Thermal table scope bounds absent from requirement | 15/46 | 0/46 | T01–T15 |
| Fire-table occupancy scope still unannotated | 2/46 | 2/46 | M01, M02 |
| Referenced fire-duration context and alternatives | 1/46 | 1/46 | M10 |
| Material classification digits treated as numeric quantities | 1/46 | 1/46 | M15 |
| French spelled-out fraction grounding | 2/46 | 2/46 | A05, A08 |
| Alternative/enumeration interpretation | 2/46 | 2/46 | A01, A07 |

A05 also has an alternative/enumeration diagnostic. M02 additionally drops
table count/width figures in its frozen representation. These are diagnostic
groups, not independent proof that every rejection is incorrect. No lexicon
or context guard was bypassed to raise retention.

The 8/46 entity-binding rejections all require entity inventories absent from
the active catalogue: M09 isolated step groups; A02 level changes; A03
sidewalks; A04 curb cuts; A11 and A13 passages; A12 direction changes; A15
entrances. A proposed fact cannot create those inventories or certify their
completeness. This round adds no entity detector or plan computation.

M11 and A10 remain context/standard dependent (2/46). Per-case diagnostics are
in `reports/slot-oracle-applicability.json`. The fourth document is untouched.
