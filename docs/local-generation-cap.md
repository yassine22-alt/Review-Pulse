# Local generation-cap investigation

The fixed cohort is the 24 cases in `reports/local-24-cohort.json`: 21/24
ended at the generation cap and 3/24 at source-subject grounding. The original
client discarded response text before raising on a length finish. Historical
raw output is therefore unavailable for 21/21 cap cases; it cannot honestly be
classified after the fact.

Instrumented replays use the same Qwen2.5 1.5B model, temperature zero, seed 42,
8,192-token context and 4,096-token generation cap, with streaming transport to
preserve output incrementally. Diagnostic replay may stop early when repeated
invalid node records establish a loop. These are new replays, not recovered
historical responses or a new accuracy benchmark.

The initial captured draft repeated one identical node, with the same ID and
operands, 58 times. Operands contained source quantities instead of references
to fact/literal nodes. A larger cap would not repair that graph. Replays of the
remaining cap cases are captured separately; do not generalize the initial
example to cases whose output has not been inspected.

The minimal fix exposes a schema-derived wire contract in the prompt and
states that IDs are unique, references contain IDs, and context provides
definitions rather than additional obligations. Operator symbols come from
the existing expression-language registry. The constrained decoder stays on;
model, seed, context, timeout and token cap stay unchanged. No clause-specific
examples, thresholds or room names were added. The compiler rejects duplicate
node records even if a generation finishes.

The client now retains response text on a length finish and clears stale
diagnostics before a new request. The evaluation runner can capture local raw
responses explicitly with `--raw-dir`; this is opt-in, not a public log.

The paired rerun must use exactly the same 24 IDs and list terminal stages,
retained IR and correctness separately. Its results are pending until it
finishes. Compiler tests do not demonstrate improved local model accuracy.
