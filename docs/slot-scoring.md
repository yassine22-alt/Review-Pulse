# Slot scoring before validation

Score the initial and final captured model drafts separately. Never select the
best attempt. Subject, fact, operator, value, unit, metadata applicability and
clause span receive independent exact-agreement counts and denominators.
Retention remains a separate pipeline result.

The scorer reads raw JSON before schema, span, ownership or verifier checks.
Truncated responses retain completed fields/items; missing requested fields
count incorrect. Facts and operators are normalized sets, so node-ID reuse
does not cause a mismatch. Values use SI normalization, units use dimensions
(with counts distinguished), and categorical literals are included. Span
agreement requires the frozen clause identifiers and quotations. Atom-level
matched/gold/predicted counts expose partial credit even when exact field
agreement is zero. This does not measure correct association of an operator
with a particular fact, legal equivalence or end-to-end accuracy.

Unknown fact-name aliases are not inferred. Subject phrases use the frozen
labels and the supplemental author-approved thermal header phrases. The old
expression interface does not request a subject field: that slot is N/A, not
a model error. Applicability scoring currently has gold annotations for only
15 thermal clauses. The other 31 are N/A for metadata scope scoring, not
assumed unrestricted. Labels have no independent review.

## Existing-output rescoring

No model was invoked for these numbers. Cohorts are not pooled.

| Final captured slot | Bounded local run | Prompt-only local partial | Diagnostic cap replays |
| --- | --- | --- | --- |
| Raw cases available / planned | 16/24 | 2/24 | 21/46 |
| Subject exact | 0/16 | 0/2 | 0/21 |
| Fact exact | 0/15 | 0/2 | 0/20 |
| Operator exact | 0/14 | 0/2 | 0/19 |
| Value exact | 0/9 | 0/1 | 0/11 |
| Unit exact | 0/9 | 0/1 | 0/11 |
| Annotated applicability exact | undefined, 0/0 | undefined, 0/0 | undefined, 0/0 |
| Clause span exact | 13/16 | 0/2 | 1/21 |

There are 16 raw bounded-run cases but only 15 completed pipeline cases:
one draft was captured before the run was stopped. Pipeline retention is
0/15 completed. The nine uncompleted cases are not semantic failures.
The replays were stopped early on repetition and are diagnostic evidence,
not recovered historical responses or a comparable full model run. They
have 2/34 gold fact atoms matched despite 0/20 exact fact-field matches.

Earlier hosted raw outputs were not retained. Their final reasons and
evidence requests cannot reconstruct model slots. Historical hosted slot
accuracy is therefore unmeasured (all field denominators 0), not 0% accuracy.
Both original hosted reports and the later T01 pilot have this limitation.
New response recording stores candidate responses locally before validators,
including rejected drafts, while excluding request text, headers, credentials
and exception messages. Transport failures have no slot score unless an
earlier actual draft exists; they are never counted as semantic failures.

Reports are `reports/local-schema-slot-scores.json`,
`reports/local-wire-slot-scores.json`, `reports/local-replay-slot-scores.json`
and `reports/hosted-old-*-slot-scores.json`. Each lists every selected case,
first/final attempt scores, raw trace locations or an explicit missing status.
No fourth-document data is read by this scorer.
