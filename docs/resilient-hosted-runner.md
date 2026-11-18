# Resumable drafting runs

`scripts/run_development_drafting.py` loads all 46 development obligations.
The default batch size is four and concurrency is one. Each completion gets
at most three HTTP attempts. HTTP 429 and 503, selected server failures and
network errors use exponential backoff with jitter, capped at 60 seconds.
Retry-After is respected within that cap. Exhausting an obligation's request
attempts opens the client's circuit for the rest of that batch cycle.

A failed batch is retried for at most three full cycles. Completed
obligations are cached. Only unavailable obligations are retried. After the
third failed cycle the run stops and lists the pending IDs. A later explicit
invocation can resume from the same cache.

Cache keys include the source and clause context, runtime catalogue, model,
backend, generation budget, timeout, interpreter implementation and transport
implementation. Credentials are excluded. Writes are atomic. API_UNAVAILABLE
is never stored as a completed result. Corrupt cache entries cause a miss.
Changing code or settings requires a new output report. The cache retains
valid results for matching fingerprints.

Each batch reports request errors / request attempts, unavailable obligations /
attempted obligations, cache hits and HTTP status events. Failed connections
also count as failed request attempts and have a null HTTP status. A denominator
of zero is undefined. API_UNAVAILABLE outcomes are excluded from semantic
failure counts, even when the original pipeline catches a transport exception
and returns its own UNRESOLVED status.

## Initial offline preflight

At this earlier checkpoint no `GEMINI_API_KEY` was present. The
[attempt report](../reports/hosted-resilient-attempt.json) records
MISSING_ENV_CREDENTIAL, 0/0 request attempts, 0/46 semantic evaluations and all
46 obligations pending. No batch was submitted. No claim about provider
availability or model interpretation follows from this preflight.

## Replacement credential after Windows restart

The process can now read GEMINI_API_KEY. Google's model-list endpoint
authenticated the replacement key; no credential value was printed or stored.
Gemini 3.8 Flash's small generation probe timed out on 3/3 attempts at 45
seconds each. A listed Gemini 2.5 Flash alternative returned HTTP 404 on 1/1
attempt. Model listing does not prove usable generation or quota.

The original-pipeline run used 8,192 output tokens, 45-second requests,
concurrency one, batch size four and three retry cycles. The first batch
recorded 3/3 request errors in each cycle, 9/9 overall: 7/9 HTTP 429 and
2/9 network timeouts. The circuit marked 4/4 batch obligations unavailable
per cycle and prevented further calls within each cycle. After cycle three
the run stopped: 0/46 semantic evaluations, all 46 pending. The remaining
42 obligations were not submitted. Wrong approvable / approvable remains
undefined, 0/0. The 45-second budget is not a completed model capacity test.

At that checkpoint the redesigned hosted comparison and fourth-document run
had not been submitted.
[Original-pipeline availability report](../reports/hosted-original-replacement-key.json)
and [credential preflight](../reports/gemini-replacement-preflight.json) retain
only non-secret statuses and request counts. The interrupted restricted-process
probe is not a completed retry cycle. A separate credential-free curl check
reported a Windows TLS identity error under the restricted process; public TLS
and authenticated model listing succeeded under the normal Windows identity.
Generation failures still occurred under that normal identity.

No billing setting changed. Error bodies did not identify the quota subtype.
The user subsequently supplied the AI Studio dashboard: Flash showed 22 used
against 20 daily, Hydrogen 3/20 and Gemini 3 Flash 1/20. These values are
user-transcribed, not independently verified. Only the Gemini credential is
configured. Other providers were not called. The runner stopped after three
cycles before the new quota information justified a different-model test.

Five automated tests passed. They cover missing credentials, HTTP 429 and
503 backoff, bounded attempts, circuit behavior, concurrency, structured
schemas, credential redaction, cache resume and fingerprint invalidation.

## Quota-aware follow-up

`--min-interval 13` spaces actual requests, including retries, to respect the
reported five-requests-per-minute allowance. `--request-budget 8` caps all
HTTP attempts across clauses and retry cycles in one invocation. Failed
attempts consume the local allowance conservatively. Cache hits do not.
Starting a new cycle resets the circuit, not the allowance. No request is
sent once it reaches zero. The report records REQUEST_BUDGET_EXHAUSTED as a
client limit, not a semantic error or an extra failed HTTP request.

Budgets apply per invocation. Before resuming, use the actual remaining
project allowance; the runner cannot see other applications' usage. It does
not automatically resume at midnight. Google's daily limits are per project
and reset at midnight Pacific time. See [official limits](https://aistudio.google.com/docs/rate-limits).

Using the quota the user reported, the strongest listed model,
`gemini-4-hydrogen`, received eight requests per arm, with 13-second spacing,
8,192 output tokens and 180-second timeout. Both arms completed 2/46 clauses,
retained 0/2 and recorded 0/8 request errors. Each stopped during the third
clause at its budget; the other 43 were not submitted. No fourth-document
request was made. These are incomplete development results, not a full
ceiling or an accuracy improvement. Models are not pooled.

[Original run](../reports/hydrogen-original-development.json),
[structured run](../reports/hydrogen-structured-development.json) and
[assessment](../reports/hydrogen-development-assessment.json) retain counts
and per-obligation blockers. Two new budget/pacing tests and the five existing
runner tests passed 7/7. They check that retry cycles do not replenish the
budget, timeouts consume allowance, pacing includes elapsed backoff, and
budget exhaustion fabricates no HTTP failure.

## Run instructions

The user selected free quota over multiple days. The
[frozen continuation protocol](free-quota-continuation.md) describes the
running worker, daily accounting, stop control and reboot recovery. It
reserves allowance before calls, retains uncertain usage after interruption,
and does not touch the fourth document or approve interpretations.

Set the rotated key as `GEMINI_API_KEY` in the environment available to the
process. Do not place its value in a command, report, example, `.env` file or
chat. Then run:

```text
python scripts/run_development_drafting.py access.txt reports/hosted-current.json --backend gemini --model gemini-3.8-flash --batch-size 4 --cycles 3 --max-tokens 8192
```

For the original pipeline use a clean checkout of
`3579622d166e64a2d9831c7c9ee95bb3e4ba4fef` and pass its `src` directory
through `--original-src`, with a separate report. Rule source, runtime
catalogue and generation settings must match for a paired comparison.
The runner sends regulation text and the declared rule vocabulary. It sends
no plan images, geometry, measured plan values or ground-truth verdicts.

## Other providers and billing

No hosted credential variables were configured in the preflight process.
Existing adapters can be configured for OpenAI-compatible endpoints, Groq,
OpenRouter, Mistral, Cloudflare and Anthropic. They require the corresponding
provider configuration and an environment credential. No request was made
to another provider.

The earlier Pro response reported zero free-tier quota. To enable Gemini's
paid tier, open the intended project in AI Studio, select **Set up billing**,
link an active Google Cloud Billing account and complete the offered payment
plan. Google currently describes a minimum $5 prepayment for new Prepay
accounts. Check the project's tier and actual model limits afterward.
Flash can use eligible free-tier quota. The 503 responses alone do not
establish that billing is required. [Official billing instructions](https://aistudio.google.com/docs/billing).
