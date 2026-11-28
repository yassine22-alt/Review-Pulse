# M34: our proposal's requirements against what is built

Written 28 November 2026, against branch `product-app`. It compares every functional and non functional requirement of our
capstone proposal (version of 18 October) with the code.

**How to read it.** *Built*: code for it exists and is reachable from the web app (or the command line where the requirement does
not ask for a screen). *Partial*: part of it works; the missing part is named. *Missing*: not there. These statuses come from
reading and searching the code on this date. They are **not** acceptance results: no plan reviewer has confirmed any of them, and
the test cases of our test plan are run separately. M, S and C are the proposal's priorities (must, should, could).

## Functional requirements

| ID | Pri. | Requirement, short | Status | What is missing |
| --- | --- | --- | --- | --- |
| FR-01 | M | Signed in user creates a project: name, occupancy, location, rule set | Partial | No occupancy or location field |
| FR-02 | M | Upload PNG, JPG, PDF, SVG up to 50 MB | Built | Also DXF, DWG, TIFF; limit 200 MB |
| FR-03 | M | Tell vector from raster by itself | Built | |
| FR-04 | M | Each upload an immutable version named by content hash | Built | Added 28 November: every drawing is kept under its content hash (requirement documents are still replaced) |
| FR-05 | M | Find the scale and record how | Built | |
| FR-06 | M | Walls, doors, windows, stairs, rooms, annotations with confidence | Built | Confidence is a tier per element; accuracy on real drawings is low (below) |
| FR-07 | M | Read French and English labels and dimensions | Built | |
| FR-08 | M | Find rooms, type them, compute areas, tell corridors apart | Built | |
| FR-09 | M | Room graph with typed edges and exits | Built | |
| FR-10 | M | A verdict per applicable rule and element | Built | |
| FR-11 | M | Seven check classes | Built | |
| FR-12 | M | Finding carries element, values, severity, clause, confidence, evidence | Built | |
| FR-13 | S | Live progress, and cancel | Partial | No cancel |
| FR-14 | M | Plan with verdict overlay, selection both ways | Built | |
| FR-15 | M | Switch between original, what was detected, and violations | Built | Added 28 November: plan only, what was read (rooms and elements, with their counts and a warning that reading can miss), corrections |
| FR-16 | M | Filter findings by severity, rule family, room, status | Built | Added 28 November. A comment is tied to a room through the room or element its check names; a comment about the whole sheet has no room |
| FR-17 | M | Accept, dismiss with a reason, assign, resolve; audit log | Built | Added 28 November. The assigned person sees it on their work page; no email is sent. A "resolved" made on earlier drawings is flagged for a new look |
| FR-18 | S | Re check a revision: resolved, persisting, new | Built | In the app since 28 November ([M27](M27_back_check.md) for what was measured): each earlier comment gets a reading the reviewer checks; changes nobody asked for are counted |
| FR-19 | M | Annotated PDF, JSON and CSV | Built | |
| FR-20 | C | BCF issues | Built | |
| FR-21 | S | Dashboard with open findings and a readiness score | Partial | A work queue; no readiness score |
| FR-22 | M | Knowledge graph of clauses, conditions and the elements they apply to | Partial | References, definitions, tables and exceptions between clauses; the link to element classes lives in the rules, not in one graph |
| FR-23 | S | Upload regulation text, get drafts linked to their source | Built | |
| FR-24 | M | Approval before a rule runs; every rule set versioned | Partial | Approval yes; rule sets carry a version field that the app does not advance |
| FR-25 | S | Custom rules by file or form, tested on a sample plan | Partial | By file and command line; no form |
| FR-26 | S | Chat assistant grounded in findings and clauses | **Missing** | |
| FR-27 | M | The assistant cannot change verdicts | Missing with FR-26 | |
| FR-28 | M | Organisations, users, roles with permissions | Partial | Roles are admin, coordinator, reviewer, applicant; the proposal names engineer, project manager and curator too |
| FR-29 | M | Delete a project and everything derived | Built | |
| FR-30 | M | Split sets into sheets and classify each | Built | |
| FR-31 | M | Link dimensions and check chains | Built | |
| FR-32 | M | Door and window tags linked to schedule rows | Built | |
| FR-33 | S | Fixtures and door swings: clearances and conflicts | Partial | Swing conflicts; fixture clearances not done |
| FR-34 | S | Align two sheets and overlay them | Partial | Automatic alignment inside the back check; no three point manual way, no screen |
| FR-35 | S | Compare revisions element by element | Partial | Words, shapes and schedule rows are compared, not building elements |
| FR-36 | C | Site plan: setbacks and coverage | Missing | |
| FR-37 | M | Link storeys through stairs and check routes across floors | **Missing** | Levels are read from titles; no route crosses floors |
| FR-38 | M | Exits defined per rule pack | Partial | The proposal's default definition works, but it is fixed in the code |

## Non functional requirements

| ID | Requirement, short | Status | What is known |
| --- | --- | --- | --- |
| NFR-01 | One storey plan analysed in 60 s median | Not measured against this target | The 22 sheet set takes about 11 minutes on a 6 GB laptop |
| NFR-02 | Screen actions within 200 ms, page load 2 s | Not measured | |
| NFR-03 | Four workers give 2.5 times the throughput | Missing | One server process |
| NFR-04 | Accuracy objectives O1 to O4 and O7 | Partly measured, partly missed | See below |
| NFR-05 | No FAIL from unscaled geometry | Built | |
| NFR-06 | Every finding traceable | Built | |
| NFR-07 | Same input, same verdicts; versions recorded | Partial | Verdicts come from deterministic code; search order was made repeatable ([M32](M32_part_by_part_and_vision.md)); model versions are not recorded on every run |
| NFR-08 | TLS, encryption at rest, role checks, OWASP review | Partial | Role checks on every route; no TLS or encryption of its own, no OWASP review |
| NFR-09 | No drawing to an outside AI without consent | Built | Pictures of drawings are refused for outside models altogether |
| NFR-10 | 95% availability in the pilot | Not applicable yet | No pilot |
| NFR-11 | Usability score of 70 or more | Not measured | Needs users |
| NFR-12 | French and English interface and reports | **Missing** (interface) | Documents in both languages are read; the screens are English only |
| NFR-13 | Rules change without code; 70% back end test coverage | Rules: built. Coverage: not measured | |
| NFR-14 | Containerised, one command install | Not verified | A Dockerfile and compose file exist; not rebuilt since the new web app |
| NFR-15 | Clear message on bad input, no crash | Partly tested | |

## Objectives with numbers (proposal, Table 1)

| | Target | Measured |
| --- | --- | --- |
| O1, O2 | Walls and doors on raster, and vector symbol classes | **Missed on real drawings:** on 100 FloorPlanCAD drawings the rules reached F1 0.28 for walls, 0.66 for doors, 0.20 for windows. On generated plans nearly all are found, which says little about real ones |
| O3 | Room precision and recall 0.85 | Generated plans: 1.0. FloorPlanCAD, 40 drawings: room F1 about 0.74 |
| O5 | 40 curated requirements from two sources and 15 consistency checks | **25 rule files** in the starter pack |
| O6 | Precision and recall of rule drafting | Measured ([M11](M11_second_pass.md), [M12](M12_checklist_benchmark.md)) |
| O7 | Errors found on an independent benchmark | Generated plans with planted errors only; no independent real benchmark |
| O8 | 60 s median per sheet end to end | Not measured as a median |
| O9 | Usability study with six practitioners | Not done |

The numbers in this table are quoted from the experiment log ([NOTES.md](../../NOTES.md)) and the progress notes, from the dates
written there; they were not rerun for this page.

## Count

Counted from the table: of 38 functional requirements, **23 are built, 11 partial and 4 missing** (FR-26, FR-27, FR-36, FR-37). Of the
27 marked must, **20 are built and 7 are not fully built**: FR-01, FR-22, FR-24, FR-27, FR-28, FR-37, FR-38.

## Order of work

1. Must requirements that are small or already half there: FR-38 (exits per pack), FR-01 (occupancy, location). Done on
   28 November: FR-04, FR-15, FR-16, FR-17.
2. The back check in the app (FR-18, FR-35): built and measured already, and it is the step after the first review.
3. The test cases of the test plan, run and recorded with their actual results.
4. FR-37 (routes across floors): the one large must requirement.
5. As time allows: FR-26 with FR-27, FR-21, FR-13, NFR-12, NFR-13, NFR-14.
