# Minimal scope-separated hosted pilot

Only the 12 IDs in the first three phases of `development-pilot.json` are
eligible. The fourth document and the other 34 development obligations are
excluded. There is no new quota worker, provider switch or billing change.

This is a new first-draft experiment, not the historical production-pipeline
comparison. Both arms get the same regulation context, runtime catalogue,
metadata vocabulary, subject field, fact-declaration option and source fields.
The expression arm uses the existing expression language; the structured arm
uses typed node slots. Both carry project metadata separately. Prompts contain
no benchmark answers or clause-specific examples. Both use Gemini 4 Hydrogen,
temperature zero, 8,192 output tokens and one candidate; no triage model,
cascade, critic or repair call. Both feed the same deterministic compiler gates.
Retained drafts still require human approval.

Raw fields are scored before those gates. Each result records slot scores,
retention and terminal stage. The saved report resumes completed cases and
rejects changes to code/model fingerprints. No best-of selection or silent
pooling with historical arms is permitted. A maximum HTTP-attempt allowance
and the existing retry/pacing code bound a single invocation. This is a finite
command, not a standing scheduling protocol.

## Attempted run

The initial code (`be4165d7f6a16db70ca65fb4ca5517663cf4984a`) completed
0/12 obligations in either arm. The first structured case had 3/3 HTTP 503
responses. A second invocation returned HTTP 400 on 1/1 request. This is a
request rejection, not model failure or quota exhaustion. No response slots
were generated; retention and all slot accuracies have denominator zero.

A separate single-request diagnostic then received HTTP 429 (1/1). Its error
body was read only in memory; no message was displayed or retained. No further
API calls were made. It is separate from the four pilot attempts. Total
requests this round: 5/5 non-successful (3 service, 1 request, 1 quota).

The exact HTTP 400 cause is not known because the original client intentionally
discarded error bodies. A complex schema is a candidate explanation, not a
confirmed diagnosis. Google's [structured-output documentation](https://aistudio.google.com/docs/structured-output#simplifying-complex-schemas)
explains that counted arrays can expand decoding state and suggests removing
their bounds. The native hosted adapter now removes array counting bounds
from a copy of the decoding schema. Compiler-side structural/diagnostic limits
and typed minimum sizes remain enforced. The local decoder is unchanged.
Tests verify both properties. Server acceptance of this revised schema is
NOT measured; no call was made after the diagnostic quota rejection.

The pre-adaptation run stays in `reports/scoped-first-draft-pilot.json`, with
its integration-error classification corrected explicitly. Use a new result
file for the revised code; do not change its recorded fingerprint to resume it:

```powershell
.venv/Scripts/python.exe scripts/run_slot_pilot.py <local-accessibility-text> reports/scoped-first-draft-pilot-v2.json --budget 24
```

This can finish in one invocation when provider availability and request quota
permit; a key or billing change is the user's decision. No new local model
benchmark or fourth-document run is authorized by this command.

## Decision rule

Five structured thermal outputs must be available, with all seven gold slots
eligible (35 slot judgements), before applying the requested 70% rule. Request
rejections and API-unavailable responses never become zero-accuracy samples.
Current evidence is 0/5 thermal outputs and 0/0 scored slots. The decision is
therefore NOT_YET_MEASURED; neither repositioning nor a next-measurement claim
is justified yet. Strict normalized slot agreement is not semantic rule accuracy.
