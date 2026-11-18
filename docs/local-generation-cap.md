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
to fact/literal nodes. All 21/21 instrumented replays are now complete:
20/21 exhibit repeated invalid node records or IDs; 1/21 exhibits a repeated
prose explanation during repair after an invalid but completed draft. These
are overlapping call-level symptoms, not mutually exclusive model verdicts.
The first eight replay case summaries incorrectly called their early stop
whitespace repetition; their captured call records identify node repetition.
The reviewed summary corrects that label. Raising the cap is not justified by
this evidence. Raw JSONL stays local; the shared report retains classifications
and trace paths.

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
The wire-contract fix has already produced another length-finished repetitive
response in the rerun, so cap failures have not been eliminated. Do not present
the change as a successful accuracy fix while the cohort is incomplete.

That prompt-only run was superseded after a transport timeout interrupted the
first batch. Its single completed semantic case stopped at source-span
grounding; it is not a 24-case result. A second, isolated cap-only variant
constrains node IDs and references to short `n`-number identifiers, enforces
the existing variable syntax, limits node/operand lists to 64 and bounds
unresolved explanations to eight messages of 512 characters. These are wire
budgets, not regulatory thresholds. More complex clauses may remain unresolved.
Model, seed, temperature, context, timeout and generation cap remain unchanged.
Batch size is one to persist each result and avoid a timeout opening the local
circuit for several queued cases. Transport spillover is therefore not directly
comparable; semantic outcomes and correctness remain the paired quantities.

The isolated variant excludes fact-declaration changes and has 12/12 schema
tests passing. `reports/local-cap-protocol.json` and its companion patch record
how to reproduce it. Its report is `reports/local-schema-after-24.json`; do not
pool it with the prompt-only partial run or the declaration oracle.
