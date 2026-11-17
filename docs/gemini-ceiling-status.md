# Hosted ceiling access and raster investigation

The requested new ceiling experiment is incomplete. M01–M16, A01–A15 and
T01–T15 are development inputs for this round. There are 46 planned
obligations. No obligation has a completed hosted drafting evaluation.

## API access

The supplied Gemini key successfully authenticated to Google's model-list API.
The key was read in memory and was never placed in a command, output,
benchmark artifact, environment file or Git commit. The generation requests
contained regulation text, instructions and rule schemas. They contained no
drawings, coordinates, plan measurements or truth labels.

One small regulation-only request succeeded with Gemini 3.8 Flash. This
checked API access and did not evaluate an interpretation against gold labels.
Subsequent native generation requests and a compatible-endpoint attempt did
not complete the first obligation with a successful model response.

| Model | Observed access result |
| --- | --- |
| Gemini 4 Hydrogen | Repeated HTTP 503, UNAVAILABLE, high demand |
| Gemini 3.8 Flash | One successful access check, followed by repeated HTTP 503 during drafting |
| Gemini 3.1 Pro Preview | HTTP 429, free-tier input, request-per-minute and request-per-day limits all 0 |
| Gemini 3.7 Flash | HTTP 503, UNAVAILABLE |
| Gemini 3 Flash Preview | HTTP 503, UNAVAILABLE |
| Gemini 2.5 Pro | HTTP 404, unavailable to new users |

The native M01 attempt made two logical completion calls. Each exhausted
three HTTP attempts with 503 responses. The production pipeline returned
UNRESOLVED after catching those transport exceptions. Its semantic terminal
stage is **not evaluated**. For this report the blocker is **API_UNAVAILABLE**.
M02 was interrupted during the same outage. The remaining obligations were
not submitted through the drafting pipeline.

Completed evaluation denominator is 0/46. Retained, matching, partly matching
and wrong rules cannot be scored. Wrong approvable / approvable is undefined,
0/0. These observations establish neither model capacity nor a pipeline
design failure. Drafting redesign and the fourth-document comparison await
the requested hosted baseline.

The available model list does not establish usable generation quota.
The [official pricing](https://aistudio.google.com/docs/pricing) and
[rate-limit documentation](https://ai.google.dev/gemini-api/docs/rate-limits)
describe model-specific free access and project quotas. No billing setting
was changed.

## Raster failure cause and repair

The crash originated in installed EasyOCR's recognition-model loader.
Its Latin recognition checkpoint existed with the expected byte length but
failed the upstream MD5 check. The corruption-recovery branch at
`easyocr/easyocr.py:184` uses `corrupt_msg`, which is only defined inside a
different method. This caused the observed NameError before OCR could run.

The affected file was `~/.EasyOCR/model/latin_g2.pth`, 15,406,141 bytes.
Its previous MD5 was `5add1dbeb6a3d6bb1a8aae190dbfd692`. The official
release has MD5 `469869130aad1a34e8f9086f4262bc59`. The restored file
matches that upstream checksum. The two files have equal size and
11,171,223 differing bytes. File-size checks alone would not catch this.

The replacement came from the URL declared by the installed EasyOCR package,
[the official Latin model release](https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/latin_g2.zip).
The damaged file was preserved with a `.corrupt-` suffix. The repair changed
the local model cache. No application or vendor source was patched.

## Segmentation regression comparison

The production segmentation source is identical to commit
`aa0d957120378b5cc7fc77f6cabecb956656eafb`. The checkpoint SHA-256 remains
`25951fa33d8da57b95b6e9aec9265b6c891bd7df5c0197217c453228dfe85ac6`.
Both versions ran on the same synthetic acceptance image, resized to
512 × 512, using the same environment and checkpoint.

All 262,144 class pixels agreed. The maximum probability difference was
0.0 and the rescale factors agreed. The
[comparison artifact](../reports/segmentation-regression-gemini-round.json)
records the image, checkpoint and output hashes. This verifies prediction
stability for one prepared image. New segmentation accuracy was not measured.

## Complete slow suite

The complete slow test selection passed **45/45**, with **0 failures**, **0
skips** and **948 non-slow tests deselected**, in 905.97 seconds. All five
raster acceptance cases that previously crashed passed after restoring the
recognition checkpoint. The invocation was:

```text
python -m pytest -m slow -q --tb=short --basetemp=runs/gemini-complete-slow --junitxml=runs/gemini-complete-slow.xml -p no:cacheprovider
```

The [JUnit report](../reports/gemini-complete-slow.xml) preserves every selected
test result. This run verifies the existing slow tests in the current local
environment. No held-out segmentation accuracy claim follows from it.
