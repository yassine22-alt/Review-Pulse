# Structured drafting: development experiment

The drafting entry point now treats triage as advice and always attempts a draft.
The model fills schema-constrained nodes: source subject, fact, operator, quantity,
unit, applicability, exception and source quotation. A deterministic compiler
builds the existing rule tree. The catalogue supplies names, ownership and units
at runtime. This adds no checker family or plan measurement.

The generation schema exposes only relevant fields for each operation and limits
fact, collection and citation names to the supplied catalogue and context.
Ollama receives the JSON schema through its `format` parameter; Gemini receives
it through native structured-output configuration. Provider availability is a
separate transport outcome, never an interpretation failure.

The compiler rejects missing or ambiguous source quotations, absent subject
phrases, dangling or unused nodes, undeclared facts, collections and entities,
invalid ownership, variable binding, types and units. Compatible stated units
are converted to fact units. Multiplication and division retain dimensional
semantics. The compiled tree must survive a structural slot round trip.
Existing numerical and linguistic coverage checks remain blocking. Quantities
from an explicitly cited definition can ground a threshold; target-obligation
coverage is still checked separately. One diagnostic-driven repair is allowed.

Passing these checks produces a draft requiring human approval. It does not
establish semantic equivalence with the regulation. A rejected draft carries
NEEDS_REVIEW and a terminal-stage diagnostic. Missing bindings can carry typed
evidence requests; declaring a proposed fact does not calculate it or approve
its meaning. Legacy DRAFTED/UNRESOLVED statuses remain for existing consumers.

## Offline oracle

Author-translated slots for all 46 development obligations were committed at
`7a099c8fe6fa6da0bc44a4109c4800475e89bfcb` before compilation. No model is
called by the oracle. Its active-catalogue run reproduces 5/46 frozen trees and
their behavior on 64 generated fact worlds per retained rule; 22/46 stop at
binding, 17/46 at verification and 2/46 correctly remain unresolved for missing
context or specialist meaning.

With the author's proposed fact declarations added as data, 17/46 reproduce
the reference tree and generated behavior, 27/46 stop at verification and 2/46
remain correctly unresolved. Proposed declarations are not production
capabilities. These results expose limits; they do not establish interpreter
accuracy or improved application coverage.

The verifier still rejects scoped table quantities that the earlier manual
interpretations omitted from their executable conditions, and some written-out
quantities and ratios. These guards have not been bypassed to raise retention.
Gold interpretations and oracle translations share an author and have no
independent review. The pre-existing development scope is supplied by fixtures;
unsupplied applicability discovery remains unmeasured. Finite generated worlds
and a structural round trip are not proofs of natural-language correctness.

## Reproduction and isolation

The original Qwen2.5 1.5B run at 4,096 output tokens, 8,192 context tokens,
seed 42, temperature zero and 600-second timeout evaluated 45/46 obligations;
1/46 timed out and is excluded from semantic failures. Terminal stages were
triage 24/46, source grounding 10/46, expression parsing 9/46, binding 1/46,
retained 1/46 and transport 1/46. The only retained rule omitted a width
requirement and was author-rated wrong. It was technically approvable with an
explicitly synthetic issue-free review: wrong approvable / approvable **1/1**.
This does not measure a real semantic critic. Request-level transport error
counts for that run were not instrumented and remain unmeasured. The
[assessment](../reports/local-before-assessment.json) lists every obligation.

The paired local run is not complete. Its resumed cache snapshot has 24/46
completed, 0/24 retained: 21/24 stop at the generation budget and 3/24 at
source-subject grounding. The first 20 recorded 0/60 request errors. The whole
snapshot's request counters are incomplete because interrupted batches leave
completed cache entries. The remaining 22/46 are pending. No improvement is
claimed from this incomplete result.
Zero retained rules does not demonstrate useful accuracy.

The final non-slow suite passed 978 tests, with 2 skipped and 45 slow tests
deselected, in 530.44 seconds. The JUnit report is
`reports/structured-final-nonslow.xml`. During verification, an existing
Windows cache replacement race caused a transient PermissionError on a cache
read. Reads now rebuild on OSError as writes already did; a simulated locked
cache regression test passes. The earlier 45/45 slow result is historical,
not a fresh slow run of this redesign. Segmentation code and weights have not
changed in this round.

`scripts/evaluate_slot_oracle.py` consumes the frozen development slots and
the existing source/context fixtures, and writes per-obligation diagnostics.
`scripts/run_development_drafting.py` runs real local or Gemini drafting in
resumable batches. Original and redesigned runs must use identical model,
temperature, seed, context, token budget and timeout. Cached responses are keyed
by source, catalogue, model settings and drafting/validation code contents.
Scripted model responses used in unit tests do not enter either evaluation.

The fourth document and its labels are excluded from the development loader.
No model or checker has run on that frozen document in this round.

## Partial strong-model comparison

The replacement credential authenticated after the Windows restart. Flash
exhausted its free quota; its 7 HTTP 429 and 2 timeout results are excluded from
semantic counts. With the user's remaining quota, Gemini 4 Hydrogen completed
2/46 obligations in each arm before the explicit eight-request allowance per
arm stopped the run. Each arm recorded 0/8 request errors. Both used temperature
zero, 8,192 output tokens, 180-second request timeouts and 13-second spacing.
The configured API model identifier is `gemini-4-hydrogen`; its deployed patch
revision was not retained. Google inference hardware is undisclosed. The
Windows client does not perform this hosted model's inference.

Both original cases stop at verification, with no retained rule (0/2). The
catalogue lacks explicit occupancy/floor scope facts; one trace additionally
rejects a quantity supplied by a definition. The structured arm produces
typed requests in one case and fails schema validation during repair in the
other (0/2 retained). The latter repair invents the unit `person`, which the
unit validator rejects. The generation schema does not enumerate the accepted
unit vocabulary. This is a concrete data/schema interface gap, not a reason
to bypass the unit validator or add that alias without review.

No retained rule exists to compare as exact, partial or wrong, and wrong
approvable / approvable is undefined (0/0) in both arms. Evidence requests are
proposals, not approved facts. Some requests use dimensionless units or may
ask for a classification beyond what the frozen reading needs. When the final
repair fails validation, the returned request list can be from the previous
valid frame. No accuracy or coverage improvement is established. The other
44/46 cases remain unevaluated per arm, and this sample does not settle the
capacity question on the earlier wrongly retained local width rule.

[Per-obligation assessment](../reports/hydrogen-development-assessment.json)
and [author review](../reports/hydrogen-author-review.json) preserve these
negative results. The author has no independent review. Unit-vocabulary
injection is a supported candidate for a later measured fix; it has not been
implemented or claimed to unlock additional clauses in this result.
