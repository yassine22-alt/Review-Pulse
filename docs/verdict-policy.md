# Phase 1 verdict policy

## Baseline investigation (before implementation)

The legacy engine produces a Raw result, checks missing inputs, returns PASS immediately
when violated is false, then checks tolerance, guidance, scale and element confirmation.
The runner subsequently downgrades failures for inferred room labels and applies an OCR
absence override to all presence checks on raster plans. OCR absences can be grouped.
This asymmetrically protects against false failures while allowing uncertain passes.
The compound interpreter already uses SATISFIED, VIOLATED, UNRESOLVED,
NOT_APPLICABLE and EXEMPT with three-valued quantifiers and possible/known paths.
Acceptance scoring counts PASS/WARNING/FAIL but credits WARNING and FAIL equally as
planted-error detection. Detection does not measure verdict correctness.

The saved scan baseline contains 19 PASS, 14 WARNING and 15 NOT_EVALUATED findings.
Warnings comprise seven estimated-scale, two connection and five OCR explanations.
The OCR explanation includes an isolated room, which is a connection check.

## Result contract

Each Finding now contains an assessment with the compound interpreter's Outcome
vocabulary, typed evidence_issues (code plus detail), uppercase severity,
rule_authority, and dependencies. The legacy verdict and lowercase severity remain
at the top level so existing report rendering and browser severity filters work
without UI changes. Legacy info maps to MINOR in the assessment.
Authority comes from the rule's existing is_guidance property.

SATISFIED maps to PASS. VIOLATED maps to FAIL for requirements, or WARNING for
advisory guidance and explicit legacy max_verdict caps. UNRESOLVED maps to
WARNING when a candidate finding exists, or NOT_EVALUATED for missing inputs.
The compound interpreter continues to distinguish NOT_APPLICABLE and EXEMPT.
The legacy checker does not synthesize those outcomes for rules it skips.
Old persisted findings can still be read; their assessment is reconstructed from
the old labels and is not a retroactive evidence audit.

## Measurement decision

The configurable run/decide relative_uncertainty argument defaults to 0.25.
This is an explicit provisional scale bound, not a calibrated probability.
Known scale uses [value, value]. Estimated length uses
[value * (1-r), value * (1+r)]; area uses the squared scale factors.
Other geometry and class evidence must still be confirmed before a decisive result.

For a minimum, lo >= limit is SATISFIED; hi < limit is VIOLATED; overlap is
UNRESOLVED. A maximum uses the reversed inequalities. Strict comparators retain
their strict boundaries. The existing regulatory review tolerance is a separate
input: a violation inside that band remains UNRESOLVED, without widening the
measurement interval. No existing tolerance or confidence threshold was tuned.

Scalar widths, room areas, room widths and route lengths provide numeric inputs
directly. The policy never parses formatted display strings. Mixed schedule/drawn
widths with frame allowances, ratios, escape-window combinations and consistency
checks without an explicit interval remain unresolved on uncertain scale.
Their uncertainty propagation needs separate work.

## Evidence and membership

The runner attaches OCR-omission issues only to the annotation presence function.
An isolated room on uncertain input receives MISSING_CONNECTION.
Unknown inferred classes block both pass and fail. Shared scale, geometry,
classification and annotation dependency identifiers are recorded on findings.
The compound evaluator records every fact read, connection dependency and collection
inventory. These are dependencies visited during evaluation, not a minimal proof.

Existing three-valued quantifiers are preserved. A definite counterexample can
violate a universal rule despite an incomplete inventory. Universal success requires
complete coverage. A definite existential witness can satisfy an existential rule
despite an incomplete inventory. Incomplete collections carry INCOMPLETE_INVENTORY,
including when a decisive witness is available. Empty universal scopes retain the
existing conservative UNRESOLVED behavior. No new perception completeness inference
or inventory-confirmation UI is introduced.

## Evaluation

Acceptance retains planted_found/planted_missed and adds detection_recall.
Case.verdict_truth optionally supplies subject-level expected outcomes and issue
codes. Verdict metrics use exact rule/subject keys and count missing predictions as
incorrect verdicts. Duplicate prediction keys are reported as ambiguous, not
silently assigned ground truth. Unlabelled predictions do not enter precision.
Reported metrics are verdict correctness, precision of VIOLATED, false-pass rate
among violated truth, decisive coverage over findings, and exact issue-set accuracy
on labelled unresolved cases. Undefined denominators produce null.

The old generator provides rule-level planted-error IDs, which cannot establish
truth for every subject. Those IDs alone do not support precision or false-pass
claims. Counts and explicit unit-test fixtures demonstrate the scoring implementation.
The saved scan has no annotated ground truth.

## Validation and limitations

The first regression test failed before implementation: unverified compliant metric
input returned PASS rather than WARNING. New tests cover both comparator directions,
interval boundaries, independent tolerance, annotation/connectivity attribution,
critical severity, quantifiers, dependencies and labelled evaluation metrics.
The saved-model replay and all 19 original passes are listed in verdict-policy-scan.md.

The 25% bound is a policy assumption and may underestimate actual scale error.
Geometry confirmations still use the existing mechanism. Source tiers are not
probabilities. Unsupported complex interval propagation remains conservative.
This phase establishes policy correctness on the tested cases. It does NOT show
improved accuracy; that requires a held-out annotated comparison.
