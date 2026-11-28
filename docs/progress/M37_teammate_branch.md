# M37: what we took from the `rule-interpreter` branch, and what we did not

28 November 2026. My teammate's branch (`origin/rule-interpreter`, work up to 19 November) grew beside `product-app` from a shared
base. I read it and ran its tests against our code. I did not merge it: I brought over fixes one by one.

## The rule I used

Take what fixes a wrong answer or makes the tool safer. Leave what is measured as no better, what narrows what the product can
do, and what we already do another way. A planted error must still be found.

## Taken

Their tests, run on our code, showed real bugs. These are fixed now:

| Bug | What it did | Fix |
| --- | --- | --- |
| French number words | "trente-sept" was read as 7 | A number phrase is read whole (0 to 99) |
| French negation | "pas plus de" was not turned round | A negation before a comparison reverses it |
| Mixed inches | `2-1/2"` was misread | Read as two and a half inches |
| Schedule tags | A tag listed twice with two sizes gave one of them to the element | Its sizes stay unknown |
| A forbidden connection that was not seen | Could pass although a door may have been missed | Left undecided, with a change of ours below |

Also taken: more spellings of units, a unit is no longer matched when a letter or an exponent follows it, a crashed acceptance
check counts as failed, an unreadable cache of split requirements is rebuilt, annotation evidence is named as such instead of
"missing connection", and wall features are computed in batches to bound memory (their change; I did not measure the memory).

## Changed on the way

Their guard left "no door between a garage and a bedroom" undecided on every plan that is not exact CAD. Our saved results showed
what that does on a French plan **with no garage at all**: a new item for the applicant, worded "read none; required no forbidden
link". Now:

* the guard applies only when both rooms of a forbidden pair are on the plan, or a room of unknown kind could be the missing one;
* the item quotes the requirement and says a door or opening may have been missed.

**What this costs:** on a plan that is not exact CAD and does have both rooms, "no connection was read" is never a pass. The
reviewer has to look. I accept that: the door reader misses doors, and a wrong pass on this rule is a safety error.

**What it does not cover:** a room that was not read at all, or read as the wrong kind. Every rule about a kind of room has this
limit.

## Not taken

| Their work | Why not |
| --- | --- |
| The assisted requirement reader (replaces our checked reading) | Their own results: 12 of 36 numeric requirements correct, the same before and after; on their fourth document all 17 clauses went to hand writing, with no draft. It handles less than ours |
| Slot filling experiments, a Gemini client and a result cache | Experiments tied to that reader |
| Region naming from native labels, polygonized wall faces | Their measurement shows weak transfer to real PDF files |
| Table row extraction | Tied to their pipeline |
| Project metadata and evidence requests | Overlap with what we have ([M17](M17_evidence_ledger.md), [M20](M20_project_facts.md)) |
| A change to how counts are bounded | It could let a "at least N" requirement pass on detections nobody confirmed. It needs proof that it cannot give a false pass |

The branch stays as it is; nothing in it was deleted or rewritten. "Not taken" is a statement about this release, and each line
can be looked at again with new measurements.

## Checks

On the version with these fixes: lint clean, the self-check finds the 3 of 3 planted errors on a DXF plan, a PDF plan and through
the web app, and the browser walkthrough passes with no server error. The full test run before the last change to the guard had
1558 passing tests and 2 failures: the saved result described above, and a generated schema file that needed regenerating. After
the change, those two and the tests of the changed code pass.
