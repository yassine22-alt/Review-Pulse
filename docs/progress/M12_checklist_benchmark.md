# M12: a benchmark on real checklists, and the checks that came out of it

> **Correction, 28 November 2026:** the answer keys and by-eye marks on this page were made by an AI assistant, not by a person,
> and nobody has checked them. See [who graded the answer keys](../WHO_GRADED.md).

This note is for someone who has not followed the project. It describes the first benchmark (107 lines). The splitter was fixed afterwards and the benchmark now reads 291 lines: see `M13_reading_any_document.md` for the current numbers. It says what I measured on requirement documents written by building
departments, what failed, what I changed, and what is still open. Every number can be reproduced with the commands in
`docs/RUNBOOK.md` section 6b.

## What is measured

Four public plan-review checklists (Allentown, Berkeley, Bloomfield Hills, St. Petersburg) were split into clauses. An AI assistant labelled each of
the 107 requirement lines once, in `benchmarks/checklist_labels.json`. The file holds only document names, clause ids and
labels, never document text.

| Label | Meaning | Lines |
| --- | --- | --- |
| rule_now | a floor plan with today's facts can decide it, and a correct rule is expected | 7 |
| needs_fact | it is about the plan, but the plan model does not record what it needs | 18 |
| not_plan | site, structure, electrical, paperwork | 76 |
| bundle | several requirements in one clause, so no single rule can be right | 6 |

`scripts/checklist_benchmark.py` reads every line with the real model on one synthetic plan and scores the outcome without anyone
judging by eye. A rule on a decidable line is correct only if it uses the right numbers and the right facts. A rule on a line that
should not produce one is counted as unsupported and must be read.

## Result on the local model (qwen2.5:7b, free, on this laptop)

| | First read of the real checklists | Last full run |
| --- | --- | --- |
| decidable lines that became a correct rule | 2 of 12 Allentown lines, 0 of 7 Berkeley lines | 6 of 7 |
| wrong rules on decidable lines | not measured | 0 |
| rules written where none belongs | not measured | 1 of 100 lines |

The one decidable line that stays open is an honest decline. "1 egress door required min. 32 in." does not say which dimension of the
door the figure limits, and I do not assume a convention. "Dimension and label all rooms" was first read as a statement about the sheet,
which produced a wrong rule; it is now read as a statement about rooms and becomes the rule "every room is named on the drawing".
The one unsupported rule is an emergency egress line of the Bloomfield Hills checklist that became "every habitable room reaches an
exit". The local judge accepts it, a hosted judge refuses it.

A hosted model (Groq, `gpt-oss-120b`) read the same decidable lines before its daily allowance ran out: 6 of 9 correct, 0 wrong. The
local and hosted models fail on different lines, which is why the checks below matter more than the model.

## What failed, and the general fix

| Failure seen on real lines | Fix | Where |
| --- | --- | --- |
| Rules built by a program quoted a normalised sentence, so every one failed the provenance check | cite the clause as written | `xeval/drafters.py` `citation` |
| A rule that can never fail (`true`, `room type equals room type`) passed every check | the requirement must test a measured or yes/no fact, a count or a route | `xeval/verify.py` `check_vacuous` |
| "window or mechanical exhaust" became a rule that demanded only the window | a sentence with "or" needs a rule with an `or` | `check_alternatives`, wording in `cues.yaml` |
| Short clauses had no wording checks at all (one function word was not enough to detect the language) | one unambiguous function word is enough | `detect_language` |
| "Stairways" did not name the category "stair"; "to scale" named stairs through an Italian word | a short ending is allowed, and a label counts only in the sentence's language | `_names`, `_foreign` |
| A model that names no category, or a wrong one, lost a rule the sentence plainly states | the categories the sentence names are put to the model as yes or no, in both orders | `slot_arm.confirm_named` |
| "(e.g. bedrooms, kitchen)" restricted a rule to those rooms | examples in parentheses are removed before reading | `interpreter/quantities.py` |
| "Plans must be to scale" had no arm | a direct question about the drawing as a whole, refused when the sentence names spaces | `relation_arm._sheet_requirement` |
| "Foyers greater than 60 s.f. must have an outlet" became "foyer area above 60 s.f." | a round trip: the rule in plain words is compared with the sentence in both orders; refused only when both say different | `interpreter/roundtrip.py` |
| "Habitable rooms at least 70 s.f. except kitchens" lost the exception with a hosted model | the exception is asked as what is excluded | `limits_arm._excluded` |
| A clause with several sentences was refused as a whole | each sentence is tried; the unread ones are listed as not checked | `interpreter/checked.py` |
| An unreachable model was reported as "cannot be checked" | said plainly: the clause was not read | `xeval/status.py` |

New facts in the fact graph: window height, sill height and opening area (joined from the door and window schedule by tag), window area
and window-to-floor ratio per room (unknown, not zero, when a window has no scheduled height), and whether the drawing is dimensioned.

## The relation arm, measured again

`scripts/relations_eval.py` (16 sentences about how spaces connect, in English, French, German and Spanish, and 6 sentences that are not
relations): 14 of 16 right, 2 declined, 0 wrong but accepted (11 of 16 before). Of the 6 sentences that are not relations, 4 are declined.
One of the two accepted ("Bedrooms shall have natural light" becoming "every bedroom has a window") is a reasonable reading. The other
varies from run to run with the 7B model; in the product the round trip stands behind it.

## Hosted models: what the limits are

A free tier counts tokens per minute and per day, not only requests. Four careless reruns used the whole daily allowance of 200 000
tokens, because any change to a prompt makes cached answers new. The client now reads the provider's own rate-limit headers, asks a
reasoning model for the lowest effort, stops with a clear message when the daily allowance is gone, and counts failed calls so that a
failure is never mistaken for a refusal by the model. Iterate on the local model, run the hosted one once per milestone.

## Losses I accepted

- The round trip is on by default with the local judge. On the rules of one full run it refused one invented rule and lost none of the
  right ones. The sample is small. A stronger (hosted) judge catches different cases, so when a hosted model is allowed it judges.
- A category the sentence names but the model does not confirm twice is not added; the rule is then refused by the scope check.
- Stair lines are declined on plans where no stair flight is found. The stair finder reaches about half of drawn stairs.

## Still open

- 18 lines need facts the plan does not record: wall and door fire ratings, smoke and CO alarm symbols, stair landings and handrails,
  sprinkler notes, attic access size, appliance clearances. Each is reported as not checkable with its reason.
- The labels were made by one AI grader. A person labelling them would show how much of the 5 of 7 is the labels.
- One synthetic plan was used. The measure on drawings other people made is in `M10` and `M11`.
