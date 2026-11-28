# How plan review really works, and what ReviewPulse must do at each step

Written 25 November 2026. This page is for anyone building or testing ReviewPulse. It records the real mechanism of plan review as
we could read it from public sources, maps every step to what ReviewPulse does today, and sets the bar for calling a step "working".
Where a source could not be read, or a claim comes from a vendor or a city press release, it says so.

**The rule we hold ourselves to.** A step is not working until real plan reviewers have used it on real submissions and confirmed
it. Our own tests and measures are necessary and never enough. Until a reviewer confirms a step, we write "built" and never
"working".

## 1. The user

A plan reviewer (plan examiner, plan checker) in a permit office, or an architect's own checker before submitting. They work
against a code and a checklist, they own the decision, and their name is on it. The applicant is the other user: the designer who
must answer every correction. Public sources: Long Beach, Napa County, Duluth, Riverside, SF DBI, Alameda, LADBS, Orange County.

## 2. The mechanism, step by step

| # | Step in real life | What the sources say | Source quality |
| --- | --- | --- | --- |
| 1 | Pre check by the applicant | Offices publish pre plan check checklists (SF residential pre plan check). Seattle tested an AI pre screening tool used by applicants before submission; Toronto's precheck is advisory only | Office pages; Seattle blog |
| 2 | Intake and completeness | A permit coordinator checks the package against an intake checklist (forms, fees, sets, signatures, required drawings) and can put it on hold. It is not a code check | Duluth, Riverside, vendor blogs |
| 3 | Routing and queue | The coordinator decides which reviews apply (building, structural, fire, planning, engineering) and routes the same drawings to each, with a start date and due dates per reviewer | Duluth; Oracle docs |
| 4 | Discipline review | Each reviewer checks sheet by sheet. Offices keep canned correction lists; the reviewer circles the items that apply and adds their own. LADBS says "Review corrections circled on this Plan Check Correction Sheet" | LADBS sheet (read in full) |
| 5 | Decision per reviewer | Oracle's statuses from most to least severe: Rejected, Revision Required, Approved with Comments, Approved, Not Required. The overall result is the most severe | Oracle docs |
| 6 | Correction letter | A numbered list, usually grouped by discipline or code chapter, each item with a code section in brackets and the sheet. It is not a denial; one cycle is normal | Orange County list (read in full), LADBS |
| 7 | Applicant response | Answer each comment in writing saying where and how it was addressed, cloud the revisions, resubmit. Alameda: resubmittals without written responses "will not be accepted" | Alameda page (read in full); LADBS |
| 8 | Back check and re review | The reviewer checks the answers against the new set. Bluebeam's Compare and Overlay put a cloud at every difference; comments are tracked across cycles | Bluebeam blog, Oracle, SF DBI |
| 9 | Approval and permit | All reviewers approve; stamps and signatures; permit issued. The plan check expires after a set time (180 days, 12 months or 18 months by office) | Riverside, LADBS, Orange County |
| 10 | Deferred submittals and special inspections | Items such as trusses are listed on the cover and reviewed later with the official's approval; a deferral is not a waiver of review | Orange County A6; IBC 107.3.4.1 |
| 11 | Tools | Reviewers mark PDFs as annotations in Bluebeam Studio Sessions, inside systems such as Oracle, Accela, Tyler. Drawings must be unlocked PDFs. Reviewers keep an audit trail | Oracle docs, SF DBI, Bluebeam |

## 3. What real correction comments look like

From the Orange County 2019 residential correction list (read as extracted text, 21 pages): 239 items in 14 sections, 165 of them
(69%) cite a code section in brackets, 65 state a numeric limit. Most are instructions to put information on the drawings, not
verdicts. Real wording:

- "Show a 7' minimum ceiling height for habitable rooms, hallways, and portions of basements containing these spaces. [CRC R305.1]"
- "Habitable rooms shall have a floor area of no less than 70sf [R304.1]."
- "The minimum width of hallways shall not be less than 36". [CRC R311.6]"
- "Revise plans to show UL 217 rated smoke alarms: ..."
- "Note on plan 'Each pane of safety glazing installed in hazardous locations shall be identified ...'"
- "Revise plans at door from ________ to show compliance." Many items have blanks the reviewer fills in.

What this means for us. (a) The reviewer's output is a marked up canned list with code citations and sheet references, so that is
our output. (b) Many items are "show or note this on the plans", which is a presence check with a quote as evidence: the evidence
layer of M15 is the right tool. (c) Items that carry a limit ("36 inches", "70 sf", "7 ft") are the measured rules of M12.
(d) The public correction lists are themselves a real requirement document in the exact form our users hold, and we have not yet
run them through ReviewPulse.

## 4. Where ReviewPulse stands against each step

Status words: **built** means code and our own tests exist. **Confirmed** means a real reviewer used it. Nothing is confirmed yet.

| # | Step | ReviewPulse today | Gap |
| --- | --- | --- | --- |
| 1 | Pre check | The app runs a plan against a requirement document and reports | No advisory framing, no applicant view |
| 2 | Intake and completeness | The drawing set model reads the sheet index, title blocks and scales (M16); project facts read use, storeys, sprinklers (M20). Built, not wired to a completeness report | A completeness check against an office's intake checklist; Seattle reports 87% on completeness, with the method undefined |
| 3 | Routing | Clauses are not tagged by discipline; sheets are not tagged by discipline | Tag clauses and sheets by discipline so each reviewer sees their share |
| 4 | Discipline review | Measured rules (8 of 10 decidable lines, 0 wrong), mention rules, note evidence for 17 of 46 lines, wired ledger and sheet tables | The canned lists are ingested as ordinary documents but their "show or note this" items are not treated as presence checks with an exact place on the sheet |
| 5 | Decision | Three valued verdict; unknown is never a pass | Map to the reviewer's statuses; add "information requested" as its own state |
| 6 | Correction letter | Findings with quotes, per clause | No export as a numbered list with code citation and sheet; no marked up PDF |
| 7 | Applicant response | None | A response sheet per comment with sheet reference |
| 8 | Back check | None | Compare two versions of a set (the drawing set model gives views to compare) and re check each earlier comment |
| 9 | Approval | A person approves each rule | A sign off record per reviewer, discipline and cycle |
| 10 | Deferred submittals | Not modelled | A "deferred" state that is neither missing nor failing |
| 11 | Tools | Own web app | PDF annotation output (callout on the cited sheet) that opens in Bluebeam; an audit trail |

## 5. What the evidence says about AI in this setting

Read: Seattle's CivCheck blog (the 403 on the full evaluation report means we have only the summary), Toronto's AI register
entry, Honolulu and Denver press items. Findings: Seattle compared the tool with staff on real applications and reports 87% for
completeness checks and 92% for design compliance, accuracy rising during the test, without defining the measure or giving false
positive and miss counts. Its stated concern is coverage of the corrections a reviewer would find: a tool that finds only some
leaves the same number of review cycles. Toronto keeps the tool advisory and has staff review every application independently.
Honolulu's figures (73 days to 32.5 days, 3.4 cycles to 1.4) come from 19 permits and the city's own words call that small. No
source gave a false positive rate. We therefore treat every published speed figure as a claim to test, not a benchmark.

## 6. The bar for "working"

A step is working only when all of these hold on real submissions with a real reviewer:

1. **Coverage against the reviewer.** Of the corrections a reviewer writes for a submission, the share we also raise or point at
   (recall on real correction comments), with every miss read. Needs real pairs of a drawing set and its correction letter, from
   public records requests or office portals. We have none yet.
2. **No false pass.** Zero cases where we say "meets" and the reviewer finds a violation. This one is absolute.
3. **Few false alarms.** The share of our findings the reviewer dismisses, reported by topic, so noise is visible.
4. **Time.** Minutes per review with and without us, on the same submission, measured with ykram051's timed workflow.
5. **Edit burden.** How many edits a reviewer makes to what we propose before they sign it.
6. **Fit.** The reviewer can paste our output into their correction letter or open our markup in their tool without rework.
7. **Trust.** The reviewer, asked, says which findings they would sign without checking and which they would not.

## 7. Order of work this implies

1. Run the real public correction lists (Orange County, LADBS, the checklists we already hold) through ReviewPulse and measure how
   many items become a measured rule, a presence check with evidence, or a question, and how many stay declined.
2. Build the correction list output: numbered, grouped, code section and sheet in each item, with the evidence crop, and a marked
   up PDF with standard callout annotations.
3. Add the reviewer states (information requested, deferred, not applicable) and the discipline tags.
4. Add the completeness check from the drawing set and project facts, against an office's intake checklist.
5. Add back check between two versions of a set and the applicant response sheet.
6. Run a session with at least five real reviewers on at least ten real submissions, and report the seven measures above.
7. Only then write "working", step by step.

## 8. What we could not read

The Seattle full evaluation report (access refused), the Clark County Nevada list (connection dropped), most vendor claims beyond
their press pages, and any correction letter that pairs with a specific drawing set. Six of the sources are vendor or city
marketing pages and are used for the shape of the process, not for results.

## 9. Integration, rivals and human factors (second research pass, 25 November 2026)

Read from public pages; vendor pages are marked as such. None of the connectors below has been tested against a live tenant.

**Where the tool must plug in.**

| System | What the public documentation says | What we build | Status |
| --- | --- | --- | --- |
| Bluebeam Revu and Studio | The Studio API documents creating sessions, adding a PDF in three steps (metadata block, upload to storage, confirm) and inviting users, with OAuth 2.0. Reading markups is documented; creating markups through the API is not. A snapshot merges markups into the PDF | Write standard PDF annotations into our own copy of the PDF (they open in Revu), and upload that copy to a session | Contract tested from documentation, not live |
| Accela Civic Platform | A Document Review API lets a third party create review comments on a document and check a reviewed file back in (Automation 7.3.3.5 or later) | A connector that posts our items as comments and checks in the annotated PDF, with a dry run | Contract tested from documentation, not live |
| OpenGov Permitting and Licensing | A REST API with OAuth2 client credentials and a Bluebeam integration; no comments endpoint found | A file drop, until a comments endpoint is confirmed | Limit recorded |
| Tyler EnerGov | No public API documentation found | A file drop | Limit recorded |
| Revit, Solibri, Trimble Connect | Engineers exchange issues as BCF files (topics with comments and viewpoints; BCF 2.1 and 3.0) | BCF export and import. Our findings come from PDF drawings, so the viewpoint is a page reference | Round trip tested; not opened in Solibri |
| Offices with no API | Plan check goes by email and portal upload | JSON, CSV and annotated PDF files | Built with the connectors |

**Rivals and what is now table stakes.** CodeComply.AI (floor plan checks, pre check, version comparison, comment management), CivCheck
(applicant pre screening and staff review), CrossBeam (pre check, intake screening, full plan set review, correction letters,
backchecks), UpCodes Plan Review (early access in late 2026, code database of 11 million provisions), Nomic (drawing review with PDF
markup findings), Bluebeam Max (Smart Review, tuned for US commercial). Pre check, correction letters, back checks and comment
management are therefore what a buyer expects. What a buyer cannot get from them, and what we can offer if we prove it:

1. Every finding quotes its source and the place on the sheet, and the tool abstains and says what it needs when it cannot support a claim.
2. The drawings can stay on the reviewer's machine (local models), with a hosted model only by consent.
3. It reads any requirement document in any language, including an office's own canned correction list.
4. Its numbers are measured on real documents with every loss recorded, and no claim is made until a reviewer has confirmed it.

**What the human factors studies say about the screen.** Calibrated confidence cues raised decision accuracy by about 20 points in an
AAAI 2026 study (184 participants), while miscalibrated scores gave little gain and increased automation bias. A 2026 Decision
Support Systems paper finds explanations can raise reliance as well as critical thinking. A 2026 study found a two step
workflow did not reduce over reliance and sometimes increased it. A 2026 IUI paper finds adaptive support (counter explanations when
trust is high, forced pauses) reduces over reliance. The consistent point is that engagement and calibration matter more than
more explanation. So:

- Show no confidence number until it is calibrated on our own data (conformal risk control, plan step 8); show states, not scores.
- Make the reviewer engage: the evidence crop is shown first and a finding is accepted only after it is opened.
- Audit "meets" most: a fixed share of findings that say "meets" is sent to the reviewer for a spot check, and the miss rate is logged.
- Offer the counter view when the reviewer accepts quickly many times in a row.
- Log every accept, edit and drop, since the edit count is our edit burden measure.

**Does it beat manual review?** No public source gave a controlled comparison with false positive and miss counts (Seattle reports 87%
and 92% agreement with an undefined measure; Honolulu's time figures come from 19 permits). We will measure it ourselves: the same
submissions reviewed manually and with the tool by the same reviewers in alternating order, time per review, corrections found,
false passes, and edits to our output. Until then we claim nothing about time saved.
