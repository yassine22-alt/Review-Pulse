# Timed assisted review — teammate protocol

Run the app with `rp serve --port 8081` from the repository virtual environment.
Upload/analyse a plan and a development requirements document, then open Rules
and the source-document review panel. Read individual clauses or read all;
these UI actions use `/assisted/interpret`, not archived expression drafting.
Do not include the fourth document in development reviewer sessions.

For each of 10–15 clauses, use the same reviewer name and **Start timed review**
before reading or editing. Include both numeric drafts and formalization-queue
clauses; report the numbers chosen in each group, without selecting only easy ones.
Quick fields edit facts, comparisons, numbers, units and existing scope entries.
An advanced source/context/schema editor allows a qualified reviewer to formalize
queue clauses; it starts blank. An unsupported clause is not silently drafted.
Pause during interruptions and resume before saving. Do not navigate away while
editing: unfinished sessions remain excluded, not zero-second completed reviews.

**Validate and save** logs original slots, edited slots, field-path differences,
input-event count, server elapsed seconds, pauses and rejected validation attempts.
It never approves. A separate checkbox and **Approve this rule** explicitly
attest source meaning, units, ownership, applicability and exceptions. Approval
requires a completed timed session of the same draft by that named reviewer;
a fresh source/draft invalidates stale sessions. Missing plan evidence remains
unresolved even after the interpretation is approved. No values or complete
inventories are fabricated. A second model is not required for human approval.

Review data stays in the local project's `drafts/assisted-effort.json` (ignored
by Git). The per-project `/api/projects/<id>/assisted/effort` report separates
`in_scope_draft` and `reviewer_formalization`, lists per-clause sessions, raw diff
sites, input events, seconds and group medians. Repeated sessions are not claimed
as independent clauses. Reviewer identity is self-reported; timing is elapsed
wall time excluding explicit pauses, so idle reading time remains included.
Raw field diffs are not independently graded semantic edit counts. The teammate
rubric and notes settle whether a semantic edit was needed.

Only completed sessions labelled human enter observed-effort results. Assistant,
test and open sessions are excluded. **No real completed teammate sessions have
been collected yet: observed edits and seconds per clause are not measured.**
Test clocks validate instrumentation only. Do not quote them as user effort.

For hosted drafting configure the existing OpenAI-compatible provider settings
and keep the API key in the environment only. The supplied Groq key variable can
be mapped in memory to `REVIEWPULSE_LLM_API_KEY`; never write it to `.env`, reports,
a screenshot or Git. Only regulation text and a closed fact menu leave the machine,
with the project's hosted-consent switch enabled. Local generation is not required.
