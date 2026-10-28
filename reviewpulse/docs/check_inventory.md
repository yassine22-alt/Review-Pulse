# What ReviewPulse must check: the error inventory

27 October 2026 · status of the whole project against the errors that matter

## Why this document

ReviewPulse exists to catch the errors that designers, engineers and quality controllers let through
before a plan set reaches site or a permit office. Detecting walls and doors is only the means. This
document starts from the other end:

1. which documents a project comes with, and what each one constrains;
2. which errors actually get through review, family by family;
3. for each one, exactly what ReviewPulse checks today, how reliable that check is, and what is
   still missing;
4. what to build next, in order of impact.

One principle holds throughout. No threshold is written into code: every number (a door width, a
minimum area, a travel distance) comes from the project's own requirement documents, through rules
that a person approves. ReviewPulse supplies the measurements and the logic; the documents supply
the limits. A rule that cannot be decided from the drawing says so (NOT_EVALUATED) instead of
guessing.

## 1. What review actually catches and misses

Practitioner sources agree on where errors come from, although none of them is a large ranked study:

- **Missing or conflicting information between documents is the main cause.** A project tracked in
  detail logged over 1,000 requests for information. Missing information was the most common
  cause, and design errors made up about a quarter of the architect's share
  ([RCP](https://rcp.co.nz/insights/winning-before-kick-off),
  [STRUCTURE](https://www.structuremag.org/wp-content/uploads/2014/08/D-QACorner-Schwinger-May101.pdf)).
- **Recurring examples:**
  - a door rated 30 minutes on the architectural sheets and 90 minutes in the fire plan;
  - grid lines that drift between architectural and structural sheets;
  - dimensions that differ between views;
  - room names that do not match;
  - missing tags.

  ([Datagrid](https://datagrid.com/guides/rfi-in-construction-examples),
  [QECAD](https://www.qecad.com/cadblog/?p=6422))
- **Permit review letters repeat the same items:**
  - a door in the schedule but not on the plan;
  - exit doors without panic hardware in the schedule;
  - doors swinging against the direction of escape;
  - missing clear space at doors;
  - missing accessible routes.

  ([Everett WA review letter](https://lfportal.everettwa.gov/WebLink/0/doc/1303124/Page19.aspx),
  [Wisconsin top 10](https://DSPS.WI.GOV/Documents/Programs/CommercialBuildings/BuildingInspectionTOP10.pdf),
  [UC Riverside](https://pdc.ucr.edu/media/7946/download))
- **Egress has to be traced, not just counted.** "A plan can show all the required doors and still
  have a poor egress arrangement. The reviewer needs to trace the path people will actually use."
  ([Building Code Forum](https://www.thebuildingcodeforum.com/forum/goto/post?id=279471))
- **French contracts make discrepancies the reviewer's problem.** Discrepancies between the plans
  and the written documents (CCTP) must be reported before work starts. The most time-consuming
  part of a review is the consistency between plans and technical requirements
  ([sample CCTP clauses](https://www.ligue-cancer.net/sites/default/files/clauses_communes.pdf),
  [practitioners' feedback](https://www.forumconstruire.com/construire/topic-501771-retour-experiences-redaction-coherence.php)).

So the errors worth catching are less "is this a wall" than these:

- **Cross-document consistency:** do the plan, its schedules, the area table, the brief and the
  specification say the same thing?
- **Spatial rules a reviewer must trace by hand:** routes, clearances, travel distances.
- **Silent omissions:** a missing tag, label, dimension, rating or exit.

## 2. The documents a project comes with

| Document | What it fixes | Evidence on the drawing | ReviewPulse today |
|---|---|---|---|
| Floor plans (DXF, PDF, scan) | Geometry: walls, openings, rooms, circulation | Itself | Read (all formats, scans included) |
| Door and window schedule (tableau des menuiseries) | Tag, width, height, type, quantity, sill; often fire rating and hardware | Tags on the plan | Read: tag, width, height, type, quantity, sill. **Not read: fire rating, hardware, swing** |
| Area table (tableau des surfaces) | Area per room, per dwelling, totals | Room labels and stated areas | Stated area per room read; **the table itself not cross-checked** |
| Brief or programme | Required rooms, counts, target areas, adjacencies | The whole plan | **Not read** |
| Specification by trade (CCTP) | Materials, products, fire and acoustic performance, door types | Schedules, tags, notes | Clauses split and drafted into rules; **few CCTP clauses have plan evidence yet** |
| Regulations (accessibility, fire and egress, habitability, urban planning) | Limits on widths, areas, routes, distances, exits | Geometry and graph | Drafted from the document into rules, approved by a person |
| Client or brand standards | Same kinds of limits, project-specific | Geometry, schedules | Same path as regulations |
| Sections, elevations, details | Heights, levels, stairs, steps, assemblies | Not in plan view | **Not read** (out of plan scope) |

## 3. The error inventory

Status: **Checked** (a rule exists and runs), **Partial** (the measurement exists but the rule or
an input is missing), **Missing** (needs new perception or a new input), **Out of scope** (cannot be
decided from a plan view; reported as NOT_EVALUATED).

### A. Consistency between documents (the largest source of real errors)

| Error | Why it gets through | Status | Rule / what is needed |
|---|---|---|---|
| Door or window on the plan but not in the schedule, or the reverse | Schedules are edited separately from plans | **Checked** | P-3 |
| Width in the schedule differs from the drawn opening | Revisions update one, not the other | **Checked** | K-X1 |
| Opening without a tag | Tags are added late, by hand | **Checked** | P-5 |
| Stated room area differs from the drawn area | Area tables are typed, not computed | **Checked** | K-A3 |
| Dimension chain does not add up to the overall dimension | Chains are edited piecemeal | **Checked** | K-A1 |
| Written dimension differs from the drawn length | Text overrides in CAD | **Checked** | K-A2 |
| Rooms required by the brief missing, or below their target area | The brief lives in another document | **Missing** | Read the brief or programme (room list, counts, areas, tolerance) and compare with the typed rooms |
| Area table totals differ from the sum of rooms | Totals are typed | **Missing** | Read the area table as a schedule; sum and compare |
| Fire rating, door type or hardware in the schedule differs from what the CCTP or the escape route requires | Ratings are set in three documents by three people | **Missing** | Read rating, type and hardware columns; derive which doors need them (exit doors, compartment doors) |
| Room names or numbers differ between sheets or with the area table | Each sheet is edited separately | **Missing** | Cross-sheet comparison of labels and numbers |
| Grid lines or levels drift between sheets | Copied backgrounds go stale | **Missing** | Detect grids per sheet (ArchCAD labels axis and grid) and compare between sheets |

### B. Accessibility

| Error | Why it gets through | Status | Rule / what is needed |
|---|---|---|---|
| Door clear width below the minimum | Nominal leaf width is mistaken for clear width | **Checked** | C-D1 |
| Corridor narrower than required along part of its length | Pinch points at columns and ducts | **Checked** | C-D2 (minimum clear width of the whole space) |
| No clear manoeuvring space beside the door (latch side) | Not visible without drawing the clearance | **Missing** | Clear rectangle on the pull side, from door, walls and swing; geometry already available |
| No turning circle in a room that requires one (bathroom, bedroom, kitchen) | Fixtures and furniture eat the space | **Missing** | Largest inscribed circle of the room's free floor; **needs fixture and furniture detection** |
| No clear passage beside the bed | Furniture drawn late | **Missing** | Same, with furniture detection |
| No accessible route from the entrance to the rooms that require one | Each door looks fine alone | **Partial** | Room graph and widths exist; rule combining route and widths is missing |
| Steps and thresholds on the route | Levels are in sections | **Out of scope** | Needs levels or sections |

### C. Escape and fire

| Error | Why it gets through | Status | Rule / what is needed |
|---|---|---|---|
| No exit | Rare, but critical | **Checked** | C-C1 |
| Travel distance to an exit too long | Must be traced, not measured in a straight line | **Partial** | C-T5 walks the room graph from room centre to door to door; codes measure from the farthest point of the room, so the walked distance must start there |
| Escape only through a bathroom, a WC or another bedroom | Must be traced room by room | **Checked** | C-T1, C-T2 |
| Garage opening onto a bedroom | Easy to overlook in plan | **Checked** | C-T3 |
| Bedroom without an escape window | Heights are in the schedule | **Checked** (when the schedule gives heights) | C-V2; NOT_EVALUATED otherwise |
| Exit door swinging against the direction of escape | Swing drawn by habit | **Missing** | Swing side is known for every door; compare with the direction of travel along the escape route |
| Dead-end corridor too long | Must be traced | **Missing** | Corridor geometry and graph exist; a rule for the longest one-way stretch is missing |
| Too few exits, or exits too close together, for the occupancy | Depends on occupancy, not on geometry alone | **Missing** | Occupancy from the brief or the regulation; exit separation from geometry |
| Fire-rated doors missing on compartment or stair walls | Compartments are on another drawing | **Missing** | Compartment lines (or stair cores) plus schedule ratings |
| Stair width, riser and going | Riser and headroom are in sections | **Missing** / **Out of scope** | Stair detection in plan (not yet in vector input); risers need sections |

### D. Habitability and the brief

| Error | Why it gets through | Status | Rule / what is needed |
|---|---|---|---|
| Room below minimum area or width | Partitions move in revisions | **Checked** | C-D3, C-D3W, C-D3L, C-D5 |
| Glazed area below the share of floor area | Window sizes are in the schedule | **Checked** (with schedule) | C-V1 |
| Habitable room with one door and no window | Interior rooms appear in revisions | **Checked** | C-T4 |
| Enclosed room without any door | Drafting error | **Checked** | P-6 |
| Room without a label | Labels added late | **Checked** | P-1; an unlabelled room makes type rules NOT_EVALUATED, never PASS |
| Bathroom without a WC or basin, kitchen without a sink, WC count for the occupancy | Fixtures are drawn by another person | **Missing** | **Fixture detection** (labelled in FloorPlanCAD and ArchCAD) |
| Required furniture does not fit (bed, table) | Furniture drawn as an afterthought | **Missing** | Furniture detection |

### E. Drawing quality

| Error | Why it gets through | Status | Rule / what is needed |
|---|---|---|---|
| Plan without dimensions | Export settings | **Checked** | P-2 |
| Title block without scale, revision or date | Template not filled | **Checked** | P-4 |
| Door swings colliding | Two leaves drawn independently | **Checked** | Q-1 |
| Scale stated differs from the drawing, or "not to scale" | Plotted at the wrong scale | **Checked** (in scale recovery) | Recovered scale checked against doors; NTS caps the tier |
| Text overlapping geometry or other text | Crowded sheets | **Missing** | Text and geometry boxes are known; rule missing |
| Reference to a detail or sheet that does not exist | Sheet list changes | **Missing** | Needs multi-sheet reading |

### F. Not decidable from a plan view

The following need sections, elevations, details or other trades' documents. ReviewPulse reports
them as NOT_EVALUATED with the missing input named, and never as PASS:

- ceiling heights, sill heights not in a schedule, steps and levels;
- stair risers and headroom;
- structural member sizes;
- duct and pipe clashes;
- thermal and acoustic performance.

## 4. How far each check can be trusted today

A check is only as good as the elements it measures. Findings are tiered: FAIL only when the scale
is known and the deciding elements are certain; otherwise WARNING or NOT_EVALUATED.

| Element | Generated plans (DXF / PDF) | Real CAD (FloorPlanCAD / ArchCAD) | Scans (CubiCasa5K) | Checks that depend on it |
|---|---|---|---|---|
| Walls | 0.996 / 0.995 | 0.52 / 0.40 | 0.95 | Rooms, therefore almost everything |
| Doors | 0.989 / 0.986 | 0.90 / 0.84 | 0.85 | C-D1, K-X1, P-5, route rules |
| Windows | 0.998 / 1.000 | 0.69 / 0.46 | 0.81 | C-V1, C-V2, C-T4 |
| Rooms | 1.000 / 1.000 | **not measured** | 0.90 (0.99 on ResPlan from true walls) | All area, width, route and label rules |
| Room types from labels | 1.000 | (no text in either set) | 99.95% from clean text, 53% through OCR | All rules filtered by room type |

The most important gap in this table is **rooms on real CAD**. Neither public CAD dataset labels
rooms. Walls on real CAD are found at 0.40 to 0.52, so rooms may not close. When they do not,
the room-based rules go NOT_EVALUATED rather than FAIL, which is safe but means errors are missed.
The team's own plans, reviewed by hand, are the only way to measure this.

## 5. What to build next, in order

Ranked by how often the error gets through review and how much of the work already exists:

1. **Read the brief (programme) and the area table.** Required rooms, counts and areas compared
   with the typed rooms on the plan. This is the most common class of error (missing or
   conflicting information), and the geometry is already there.
2. **Schedule columns that carry risk:** fire rating, door type, hardware. Then derive which doors
   need them: exit doors, doors on escape routes, stair and compartment doors.
3. **Escape rules that must be traced:** door swing in the direction of escape, dead-end length,
   exit count and separation by occupancy. Swing sides, routes and distances already exist.
4. **Fixture and furniture detection** on vector drawings, trained on the FloorPlanCAD and ArchCAD
   labels (toilet, sink, bathtub, bed, table and others). This unlocks accessibility clearances
   (turning circles, bedside passage) and fixture counts.
5. **Several sheets at once:** room names and numbers, grid lines and sheet references compared
   across a set.
6. **Measure rooms on real plans,** and keep raising wall recall on real CAD (ArchCAD training data
   now available).

## 6. What we need from the team

- **One or two real projects as they were actually delivered:**
  - the plans;
  - the schedules;
  - the area table;
  - the brief;
  - the CCTP;
  - the regulations and standards that applied.
- **The comment sheets of the people who reviewed them:** the bureau de contrôle, the permit
  office, or the internal quality control. Those comments are the ground truth of "errors that
  matter". Each one becomes a test case, and every miss shows what to build next.
- **The country and building types to target first** (housing, offices, public buildings). They
  decide which regulations come first, although the checks themselves stay general.
