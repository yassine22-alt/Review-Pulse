# M27: back check of a resubmission

Written 26 November 2026. This is for someone new to the project. After an applicant resubmits, a reviewer checks every comment of
the previous cycle against the new drawings. I built that step. Code: `src/reviewpulse/backcheck/`. Measurement:
`python scripts/backcheck_audit.py synth|markups|real`. Tests: `tests/unit/test_backcheck.py`. No model is used.

**Status: built, not confirmed by a reviewer, and not yet connected to the web app.**

## What it does

1. Pairs the sheets of the two versions by sheet number and title block, then by content, and finds each page's turn and shift.
2. Compares words and drawn shapes, groups the differences into changed places, and recognises blocks that only moved. Schedule
   cells are compared by row tag.
3. Finds the place of each earlier comment and tests what it asks for where that can be tested: a numeric limit, or a note that
   had to be added.
4. Gives one of five answers: resolved, not addressed, changed but not settled, moved, or cannot tell. It says what a person
   still has to check.
5. Lists changes that no comment asked for and, when the new set has revision clouds, changes outside every cloud.

It reads comments from a JSON file or from the annotations of a marked up PDF.

## A defect I found on real drawings, and its fix

Comparing the real permit set (22 pages) with an identical copy of itself reported **69 changes that did not exist**. The Florida
set against identical copies also reported changes (1 to 7 per design). My generated drawings never showed this.

Cause: real CAD exports often draw one line several times in the same place, and the shape matcher only considered the 4 nearest
candidates for each shape, so further copies stayed unmatched. Fix in `backcheck/diff.py`: identical shapes are paired one for
one first, then the rest is matched among every candidate within the tolerance. A test now draws stacked lines and requires zero
changes. After the fix, every identical, reordered or pages removed run of both real sets reports 0 changes.

## What I measured, after the fix

**Generated pairs with the truth known** (114 pairs, 210 comments):

| Expected answer | Comments | Recall | Precision |
| --- | --- | --- | --- |
| resolved | 36 | 1.0 | 1.0 |
| not addressed | 132 | 1.0 | 1.0 |
| changed but not settled | 18 | 1.0 | 1.0 |
| moved | 18 | 1.0 | 1.0 |
| cannot tell | 6 | 1.0 | 1.0 |

No comment was wrongly marked resolved. The count of unrequested changes was exact in 114 of 114 pairs. On 24 pairs that only
shift or turn the pages, no change and no wrong answer. **Read these scores with care:** the generated drawings and the checker
come from the same project, and the real defect above did not appear in them.

**Comments read back from an annotated PDF:** 3 of 3 gave the expected answer, with the text kept.

**Real sets** (`chief_architect_austin.pdf`, 22 pages; `rebuildflorida_floorplans.pdf`, 57 pages with four designs). Comments were
placed on real text lines by the script; they are not real reviewer comments.

* 12 runs of a set against an identical, reordered or pages removed copy: 0 changes reported. Comments stayed "not addressed",
  and "cannot tell" where their page was removed.
* 3 runs comparing two different Florida designs, a stand in for a heavy revision: 264 to 341 changed places, no comment marked
  resolved. I did not grade those places or answers, so this shows nothing about their accuracy. These runs took 134 to 335
  seconds each, with other jobs running on the laptop.

## Limits

* No real pair of a first and second submission with its correction letter has been tested. I do not have one.
* A demand the patterns cannot read is never marked resolved; a person has to check it.
* Scans have no vector shapes or text to compare.
* Reading facts from the full plan analysis is optional and slow, and was not part of these runs.
