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

## Current live preflight

No `GEMINI_API_KEY` is present in the environment. The
[attempt report](../reports/hosted-resilient-attempt.json) records
MISSING_ENV_CREDENTIAL, 0/0 request attempts, 0/46 semantic evaluations and all
46 obligations pending. No batch was submitted. No claim about provider
availability or model interpretation follows from this preflight.

Five automated tests passed. They cover missing credentials, HTTP 429 and
503 backoff, bounded attempts, circuit behavior, concurrency, structured
schemas, credential redaction, cache resume and fingerprint invalidation.

## Run instructions

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
