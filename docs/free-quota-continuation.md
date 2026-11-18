# Continuing the fixed comparison on free quota

The user chose free quota across multiple days on 18 November 2026. The
worker performs the remaining development drafting calls. It does not approve
rules, grade interpretation accuracy, run the fourth document, enable billing,
switch models, or automatically commit results.

The model identifier stays `gemini-4-hydrogen`. The original interpreter is
pinned at `3579622d166e64a2d9831c7c9ee95bb3e4ba4fef`; the redesigned interpreter,
source data and request runner are pinned at
`d2e803b4c7af8234ed4dace80329adaed72de7bf`. The latter is a detached checkout
outside the working project. Changes on `rule-interpreter` cannot silently
alter these runs. Source-text hash, clean pinned checkouts and dependency
versions are checked before work. Model/provider revisions behind the fixed
API identifier are not guaranteed immutable; drift remains unmeasured.

The [protocol](../reports/free-quota-protocol.json) records the non-secret
settings and runtime versions. The local machine plan is
`runs/free-quota-plan.local.json`; it contains paths, not a credential.
GEMINI_API_KEY is inherited from the environment. Its value is never written.

## Daily budget and recovery

- The project limit the user reported is 20 requests/day and 5/minute.
  The worker caps its accounting at 19/day, with 13-second request spacing.
  Other activity in the project can still consume quota.
- Two existing completed obligations per arm remain cached. The current
  window accounts for 3 prior Hydrogen requests plus the 16 measured paired
  requests, leaving zero of the worker's conservative allowance.
- The next window starts at **08:00 UTC on 18 November**. This is midnight
  Pacific in November. The fixed 08:00 reset is valid for this November–December
  protocol, not a general daylight-saving scheduler.
- The less-complete arm runs first, with up to nine requests per invocation.
  Both arms use the same model, source clauses, output budget, temperature and
  request timeout. Successful completed results are reused by fingerprint.
- Allowance is reserved on disk before starting a child. A clean exit refunds
  unused requests; an interrupted or ambiguous exit retains the reservation.
  A run crossing a reset is stopped and conservatively charged to both windows.
  No new work starts within an hour of reset.
- HTTP 429 defers work until the next window. Other availability failures that
  exhaust the existing retry circuit stop for attention. Availability and
  client-budget stops are excluded from semantic failures.

The worker stops when both sets of 46 have completed drafting. UNRESOLVED is
a completed drafting outcome, not a correct interpretation or useful verdict.
Author grading, verdict evaluation and the sealed-document protocol still
need review. It also stops on changed inputs/runtime, conflicting duplicate
results, a missing credential, a stop file, or protocol expiry on 18 December.
No inference of correctness follows from job completion.

## Running and stopping

The worker runs hidden on this PC; no startup task or system scheduler is
installed. The PC must be on and awake. A reboot stops the worker; restarting
Codex may also stop it. Its OS lock releases and its journal remains. Resume
explicitly with the same plan:

```powershell
.venv/Scripts/python.exe scripts/continue_free_quota.py runs/free-quota-plan.local.json --watch
```

Without `--watch`, it performs the currently allowed work and exits instead
of waiting for the next window. A second worker cannot take the same lock.

Progress is local at `reports/free-quota-eval/progress.json`. The journal,
per-run JSON reports and logs are in that directory; only reviewed snapshots
will be committed. To stop, create `reports/free-quota-eval/STOP`. The worker
checks it while waiting and during child execution. Remove that exact stop
file before an explicit resume. Stop and restart the worker after changing
the environment credential.

Thirteen continuation tests and the seven existing transport/budget tests passed
20/20. They cover window boundaries, prior usage, reservations, crash recovery,
cross-window accounting, changed model/source/runtime, duplicate conflicts,
zero-quota behavior, atomic state files, single-worker locking and spacing
between child processes as well as individual requests.
