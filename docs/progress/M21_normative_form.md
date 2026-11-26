# M21: the normative form (step 5, second half)

This is the second half of step 5 of `docs/PLAN_general_reviewpulse.md`. M19 read a document as a graph. Here I cut one clause into
atomic obligations and write each as a tree tied to the source words, compile it to the interpreter's `Program`, and check by logic
(not by words) that two trees say the same thing. No model was called anywhere: no Ollama, no GPU, no hosted model. Every client in
the tests is a scripted fake. Nothing existing was edited.

## What I built

| File | What it is |
| --- | --- |
| `src/reviewpulse/normative/schema.py` | the tree: `NormTree`, `Obligation`, `Scope`, `Cond`, `Exc`, `FactSpec`, `SpanRef` |
| `src/reviewpulse/normative/compile.py` | the deterministic compiler tree to `Program` |
| `src/reviewpulse/normative/equiv.py` | fact worlds, equivalence, localising the node to repair, comparison with an existing `Program` |
| `src/reviewpulse/normative/roundtrip.py` | tree to plain words (en, fr, de), the pluggable `Parser`, the exact `TemplateParser`, `roundtrip` |
| `src/reviewpulse/normative/drafter.py` | the cue arm, position balanced voting, the `Drafter` that completes a seeded tree by choices |
| `scripts/normative_audit.py` | the measures below |
| `tests/unit/test_normative.py` | 26 tests |

**The tree.** An obligation has a modality (obligation or prohibition), an optional scope ("for every room where ..." or "there is at
least one door where ..."), an applicability condition, a requirement, a list of exceptions (each with its cue words), and a list of
`unresolved` parts. Conditions are tests of a fact against a value (`ge le gt lt eq ne`, with the unit as written in the sentence) or
`all`, `any` (the alternatives), `not`. Every node can carry a character span; `NormTree` checks that spans lie in the clause and that
every fact a test reads is declared, and `ungrounded()` lists the nodes with no span.

**The compiler.** `Program` already has an `applicability` and an `exemption` slot, so the existing schema needed no extension and no
wrapper. The compiler decides where each part goes. A part that reads only building level facts goes to the slot of its own name
(outcome NOT_APPLICABLE or EXEMPT). A part that reads a fact of a member of the scope goes into the scope filter
(`forall rooms r where (...) and not (exception): requirement`). A prohibition checks `not requirement`. A number written in another
unit is converted to the unit of its fact; an incompatible unit is a `CompileError`. `unresolved` is passed to `Program.unresolved`,
so a rule with an undecided part can never say "satisfied".

**Equivalence.** `equivalent(a, b)` compiles both trees and runs the interpreter's own `run_program` on fact worlds; the outcomes
(NOT_APPLICABLE, EXEMPT, SATISFIED, VIOLATED, UNRESOLVED) must be equal in every world. The worlds are built from "cells": the limits
of both trees cut the line of every numeric fact, and one value is taken at each cut point, between two cut points, below the first
and above the last. A fact behaves the same inside a cell, so for a tree without a scope this is exact for any numeric limit
(`>=` against `>` is caught at the cut point) with no solver, whenever the product of cells is at most 2048 (otherwise a seeded
sample of at least 128 worlds). z3 is not installed here, so no SMT proof is attempted and `smt()` says so. With a scope, every
building cell is tried with 0 members and with 1 member in every cell, plus 64 random worlds of 2 to 3 members. A mismatch is
localised: each node of the first tree is replaced in turn by the node of the second tree at the same path, and the nodes whose
replacement restores equivalence are returned, deepest first (`repair`, for example `0:requirement.args[1]`).

**Round trip.** `to_words` writes the tree from fixed phrase tables in English, French and German as an indented list (a reviewer can
read it beside the sentence). A `Parser` reads the words back; `TemplateParser` is the exact inverse, a model parser plugs in with the
same method. `roundtrip(tree, parser)` returns ok or the nodes to repair. A parser that fails or returns something that does not
validate is a failed round trip, never a pass.

**Drafter.** `cue_seeds(text)` is the deterministic cue arm: from the exception and condition cues of `regs/cues.yaml` (and the inline
"EXCEPTION:" paragraph start) it finds, with spans, the segment each cue introduces. `Drafter(client, facts)` then lets the model
only choose: which fact a number limits, which direction, which yes/no fact a part states, holds or not, require or forbid. Each
choice is a position balanced vote (the options shown forward, reversed, then rotated; the answer is kept only if the orders agree).
A choice that cannot be settled goes to `unresolved`; nothing is guessed. A client follows the repo convention
`complete(system, user_json, json_schema) -> dict`.

## What I measured

All numbers come from `python scripts/normative_audit.py` (about 80 seconds, output in `reports/m21_normative/summary.json`). There is
no label and no model.

**The 30 real sentences.** I took 30 sentences that carry a condition or exception cue from the split clauses of the real documents
(ADA 2010: 9, UK Approved Document B: 6, the Allentown checklist: 8, the CAUE maisons guide and the AQC sheet: 7) and wrote each as a
tree by reading it myself; the trees are hand built, no model drafted them. Six sentences hold several atomic obligations
(for example "36 inches wide minimum ... Where two adjacent spaces are provided, 33 inches"), six carry an exception, 26 carry a condition or a scope filter.
Seven are French. For each I wrote worlds with the outcome the sentence says (116 worlds in all).

| Check | Result |
| --- | --- |
| tree validates, every node has a span, quotes are in the sentence | 30 of 30, 0 nodes without a span |
| the sentence text is found in the real document | 30 of 30 |
| compiles | 30 of 30 |
| outcome on the hand written worlds is the one the sentence says | 116 of 116 |
| round trip, tree to words to tree, equivalent | 30 of 30 in English, 30 of 30 in French, 30 of 30 in German |

**Planted perturbations.** For every node of every tree I made the single mistake a drafter makes and asked the equivalence to reject
it. 250 perturbations in all.

| Perturbation | Rejected |
| --- | --- |
| swapped direction (`>=` to `<=`) | 30 of 30 |
| dropped exception | 6 of 6 |
| dropped condition (applicability, scope filter, one conjunct) | 35 of 35 |
| wrong unit | 26 of 27 |
| wrong number (x 1.1) | 30 of 30 |
| swapped yes/no | 62 of 62 |
| dropped alternative | 3 of 3 |
| "or" turned into "and" and back | 14 of 14 |
| prohibition turned into obligation | 36 of 36 |
| "every" turned into "at least one" | 7 of 7 |
| **all** | **249 of 250 (99.6 percent)** |

The one that is not rejected is not a mistake: in the sentence "supérieure à 4%" I changed the unit of the 4 from `%` to nothing, and a
bare number takes the unit of its fact, so the two trees are equal. All 249 perturbations that change the meaning were rejected.

The same 250 perturbations also went through the round trip with a faulty reader (it reads the words exactly, then makes the planted
mistake): 249 of 250 rejected, and in 249 of 249 the `repair` list named the perturbed node or its slot. This is the same logic as
above, not an independent result, but it shows that the localisation works. Three relation sentences added 16 perturbations, 16 rejected.

**The labelled rule_now rules.** For the 10 `rule_now` items I wrote a tree by reading the sentence and compared it with the rule the
benchmark wrote (the expression in `reports/benchmark_final/rows.jsonl`, parsed by `xeval/expr_ir.py`) on fact worlds. The benchmark
declined two of the ten (item 14 and Bloomfield item 21); I still built the trees.

| Item | Result |
| --- | --- |
| Allentown 6, 15, Berkeley 2 (label part), P1, Bloomfield 2, St Petersburg 25, 48 | equivalent (7 of 7 compared; 4 sampled, 3 exact) |
| Allentown 9 | NOT equivalent, two real differences, see below |
| Allentown 14, Bloomfield 21 | benchmark declined; my trees compile and round trip |

Allentown 9, "Habitable rooms must be min. 70 s.f. except kitchens, also min. 7' in any dimension". First, the benchmark's number is
6.50321 m2, which is 3 millionths of a square metre below 70 ft2 (6.5032128), so a room of exactly 6.50321 passes there and fails in
the tree. With my limits rounded to 5 decimals this difference disappears. Second, the benchmark excludes kitchens from the width as
well as from the area. I read "also min. 7' in any dimension" as applying to kitchens too, so a narrow kitchen is a violation for me
and passes there. This is my reading of the sentence, not a proven error of the benchmark; the sentence is ambiguous, and a reviewer
should decide. It is the kind of silent difference the equivalence is meant to expose.

**Cue arm.** Against the exceptions and conditions I marked in the 30 trees: exceptions found 5 of 6, conditions found 21 of 22
(a seed counts when it overlaps the marked segment). Precision of the seeds: exceptions 5 of 5, conditions 21 of 26. Misses: "shall not
be required ... if the only means of access ..." (the cue is a condition word that I read as an exception) and "not subject to the
exception to 405.5 ... when handrails are installed". The 5 false condition seeds are cue words ("where", "when") that are not conditions.

**Drafter plumbing.** A scripted oracle client answering from the hand tree drove the drafter on the 17 sentences it can express
(one obligation, no scope, no text facts). It drafted 14 and 6 came out equivalent; in the others the drafter either put the undecided
part into `unresolved` (the rule then cannot say "satisfied") or my crude oracle could not match the question. This number says
nothing about a model; it shows that a seeded, voted, grounded tree comes out of the interface and that an abstention is recorded.

## Losses and limits

* The trees are hand built by me; the perturbations are single node and synthetic. A model makes other mistakes (several at once,
  invented facts, wrong spans). The rejection rate above is the rate on planted errors, not on model drafts.
* The round trip with `TemplateParser` proves that writing the words loses nothing (30 of 30 in three languages); it cannot show that a
  model reads the words as faithfully. The faulty reader is simulated.
* Equivalence is exact only without a scope. With a scope it is exact for 0 and 1 member and sampled for 2 to 3. When the cells are too
  many it is sampled (at least 128 worlds). z3 is not installed, so there is no SMT proof; the cell enumeration replaces it for
  numeric limits.
* A member level exception or condition becomes part of the scope filter, so for those parts the outcome is SATISFIED over the members
  left, not EXEMPT or NOT_APPLICABLE. A scope with no member is UNRESOLVED (the interpreter's rule).
* No fact against fact comparison, no arithmetic, no ratio of sums, no link or route node. The three relation sentences are written as
  yes/no facts of the room, so they are not compiled to `LinkExpr` or `PathExpr`.
* German has no real document here: the German words are written and read back for the same 30 trees. French and German words use the
  English fact labels unless a label for the language is given, so they read as a mix.
* The qualifier "when in a position that might prejudice the means of escape" on alternative b of ADB 3.99 is not modelled.
* The cue arm is cue lists only: it cannot tell a condition from a measurement definition ("lorsque le vantail est ouvert à 90°"), and
  21 of its 26 condition seeds are real.
* The sentences are 26 conditions and 6 exceptions; six exception sentences is a small sample for the exception rate.

## What a model driven drafter must do next

1. Declare the facts per document from the fact graph (`FactSpec` with labels in the document language) and give the drafter the scope
   (collection and its category values); today the facts are given by hand.
2. Extend the choice set: which collection and which category values the scope means (reuse `xeval/slot_arm.py` choices), string
   tests, "or" inside an applicability, and the cut of a clause into several obligations (one vote per candidate cut).
3. Use the round trip as the gate: draft twice with different option orders, write the first tree to words, let the model read the words
   without the sentence, accept only if both trees are equivalent; on a mismatch send only the nodes in `repair` back for a new vote.
4. Run it on the same 30 sentences and the 10 rules with a real client and report the equivalence rate against my hand trees, the
   abstention rate and the planted rejection rate side by side.
5. Wire `unresolved` and the `repair` list into the question queue of step 8, so a reviewer sees which node could not be decided.
