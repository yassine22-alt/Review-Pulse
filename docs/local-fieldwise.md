# One local decoding change

The 1.5B evaluation and its continuation guard were stopped. The last completed
pipeline snapshot has 15/24 evaluated and 0/15 retained: source span 2/15,
expression compile 1/15, source subject 11/15, types/units 1/15. Sixteen cases
have some captured raw drafting output, including one interrupted case.
Uncompleted cases are not counted as semantic failures. This remains a negative
model result; it is not grounds for tuning the 1.5B model again.

The new optional local path (`--fieldwise`, Ollama only) requests field-sized
JSON schemas: subject, metadata applicability, node structure, fact names,
operators, literal values, units, source spans and unresolved meaning.
Declarations are requested only for names absent from the catalogue. Empty
assignment groups require no call. Assignment keys are the existing node IDs;
operator choices come from the existing node forms and units from vocabulary
data. A single assembler constructs the existing SlotDraft. The same span,
type/unit, ownership, round-trip and coverage checks then apply. It supplies
no measurement or plan computation. Failed fields stay unresolved.

This changes request organization, not model weights or capabilities. The
fieldwise path makes one assembly attempt, with no repeated full-draft repair.
Several small calls can cost more than one large call; no latency or semantic
accuracy improvement is asserted. Field association and node structure remain
model responsibilities, not a correctness guarantee.

The supported backend was checked once using Qwen2.5 7B (7.6B, Q4_K_M) on CPU,
16 GB system RAM, no GPU allocation. A schema-only probe with no regulation or
plan text returned its required object, 12 generated tokens, in 30.14 seconds.
See `reports/local-field-schema-probe.json`. This proves only backend mechanics.
No new local semantic benchmark has been run. The fieldwise assembly regression
and related drafting/declaration/recording tests pass 35/35. The fourth document
remains sealed and unrun.
