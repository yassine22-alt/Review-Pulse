# Drafting diagnosis on development data

M01–M16 and A01–A15 are development data. This table codes the terminal failure from the [original 1.5B trace](../reports/morocco-interpreter-drafts.jsonl). Repair is also recorded where it ran. A triage rejection is the observed stopping point. It does not establish whether the checker could have evaluated the clause.

| ID | Terminal stage | Trace or repair |
| --- | --- | --- |
| M01 | Triage | Exit count table labelled administrative |
| M02 | Triage | Exit count and composition table labelled administrative |
| M03 | Expression parse | Invalid expression after repair |
| M04 | Generation cap | Free-form arm hit 384 tokens |
| M05 | Source-span grounding | Repaired draft quoted contextual width text outside the target |
| M06 | Expression parse | Unexpected eligibility term after repair |
| M07 | Fact ownership | Repair still read whole-building dead-end and discharge facts from exit members |
| M08 | Triage | Plan checkability rejected |
| M09 | Triage | Plan checkability rejected |
| M10 | Triage | Plan checkability rejected |
| M11 | Triage | Labelled administrative |
| M12 | Triage | Plan checkability rejected |
| M13 | Triage | Specific door type said to be unobservable |
| M14 | Triage | Plan checkability rejected |
| M15 | Triage | Plan checkability rejected |
| M16 | Triage | Plan checkability rejected |
| A01 | Triage | Plan checkability rejected |
| A02 | Triage | Plan checkability rejected |
| A03 | Triage | Plan checkability rejected |
| A04 | Triage | Plan checkability rejected |
| A05 | Triage | Plan checkability rejected |
| A06 | Triage | Plan checkability rejected |
| A07 | Triage | Plan checkability rejected |
| A08 | Triage | Plan checkability rejected |
| A09 | Triage | Plan checkability rejected |
| A10 | Triage | Plan checkability rejected |
| A11 | Triage | Plan checkability rejected |
| A12 | Triage | Plan checkability rejected |
| A13 | Triage | Plan checkability rejected |
| A14 | Triage | Plan checkability rejected |
| A15 | Triage | Plan checkability rejected |

Terminal counts out of 31 were triage 26, expression parse 2, generation cap 1, source-span grounding 1, fact ownership 1, other verifier 0, and repair-only 0. Repair ran in 4/31 and left a specific terminal failure in each case. A later prose explanation was never used to assign the stage.

The two demonstrated numeric-table false triage declines support letting numeric rows reach checked drafting. This does not establish that triage should be removed for prose, that an unbounded generation budget would recover M04, or that a new expression format would recover M03 and M06. A stronger model that succeeds under the same pipeline establishes a model-sensitive case. A stronger model that still fails only establishes that the measured configuration did not overcome the observed pipeline or catalogue barrier.
