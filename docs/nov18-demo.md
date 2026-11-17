# 18 November demo script

From the repository root, install `pip install -e ".[app,dev]"` and run
the following PowerShell commands. Choose a fresh pytest output directory.

```powershell
$env:REVIEWPULSE_LABEL_LLM = "0"
$env:REVIEWPULSE_LEARNED = "0"
python -m pytest tests/app/test_closed_loop.py -k demo_reviewed_schedule -q -s --basetemp=runs/demo-nov18
$demo = (Get-ChildItem runs/demo-nov18 -Directory | Where-Object { Test-Path (Join-Path $_.FullName "verified.dxf") } | Select-Object -First 1).FullName
rp serve --data "$demo/data"
```

The rehearsal creates the DXFs, uploads the initial plan and the requirement
document, drafts and approves two rules using a scripted model, and checks the
plan. It records both coverage pages. Its inputs are `initial.dxf`, `demo.md`,
and `verified.dxf` in the printed test run's output directory. The stored
project is **18 November rehearsal**. The automated script uses the existing
app API; it needs no model server and does not measure drafting accuracy.

1. Open the stored project and show the two source clauses in Requirements.
   The replay already loaded the document and recorded the demonstration approvals.
   To repeat the upload on screen, upload `initial.dxf` to that project.
   Confirm the fixture's door inventory after checking the drawing, then run Check.
2. Open Results and the coverage report. Article 1 is violated. Select its
   flagged narrow opening and show its evidence and clause.
   Article 2 is unresolved because one scheduled height is missing. Show the
   blank source cell in the opening table. The saved `coverage-before.html`
   is available if you need a static fallback.
3. Compare the reviewer-verified original schedule cell with `verified.dxf`.
   Upload that revision, confirm the inventory for the revision, and run Check.
   Article 2 changes to satisfied. Article 1 remains violated.
   Explain that this is verification of a **nominal scheduled value** from a
   revised drawing, and any clear-height requirement needs different evidence.
4. Show the one-page results. The demo uses a synthetic plan, two demonstration
   clauses and scripted drafting. The separate Moroccan comparison evaluates
   16 manually interpreted obligations on two frozen fact-level plans.

The app round trip is covered by the same rehearsal command. The application
uses its existing upload and review workflow. It has no inline schedule editor.

To reproduce the separate holdout comparison from the repository root:

```powershell
git worktree add --detach ../reviewpulse-holdout-baseline bc6f7892
$env:PYTHONPATH = (Resolve-Path ../reviewpulse-holdout-baseline/src).Path
python scripts/morocco_holdout.py reports/morocco-holdout-before.json
$env:PYTHONPATH = (Resolve-Path src).Path
python scripts/morocco_holdout.py reports/morocco-holdout-after.json
```
