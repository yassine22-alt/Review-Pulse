# Reproducing the Moroccan interpreter holdouts

The production code is pinned to `fe5adb42`. The fire-safety hand labels are
in `2a60396e2dcaf8df6c6032a76f6c61d6fdcef6b1`. The source manifest and
accessibility labels were pushed before model calls in
`4be77a51aa716ddf592d85186dbcd9074bc54ca7`.

The source manifest uses published French clause text, with line wraps,
punctuation and table layout normalized for the fire-safety excerpts. The
table's count and exit-composition limbs are scored separately to match the
frozen labels. The registered context bundle is assembled from the supplied
source excerpts and selected references. The accessibility excerpts are
selected by exact anchors on extracted source text. This design evaluates
drafting and execution after these source selections. Whole-PDF parsing,
reference discovery, and geometry extraction have separate failure modes.

- [Decree 2-14-499, French Bulletin Officiel annex](https://aute.gov.ma/s/a/library/2023-11-01/0a4d2c47-5b19-4b4f-858f-67f605534364.pdf).
  Downloaded PDF SHA-256 `4b95dd1a569441b43e99e4c91dc4e720689c3ea6ce42067b766c3cf901770c5e`.
- [Decree 2-11-246, French text from Agence Urbaine d’Essaouira](https://auessaouira.ma/wp-content/uploads/2015/06/decret_81.pdf).
  Downloaded PDF SHA-256 `72bce8c94d33ef696170286ccd001f03751f84cf70e1ddfe9795fb343202cb5c`.

The model receives only the excerpt, its source context and the plan
catalogue. For Decree 2-14-499 this is the same fact inventory as the
manual execution trial, with factual descriptions. For Decree 2-11-246
the catalogue comes from a frozen room-and-door fact graph using existing
bindings. It omits slope, parking and other facts that this plan reader
cannot supply. Gold meanings, expected verdicts, and reviewer-only
observations are kept out of drafting. A normalized scan checks tracked
source, tests, scripts, documentation, and corpus files, excluding these
holdout artifacts. It flags overlapping runs of nine words, or a full
four-to-eight-word excerpt. This can find copied content. It cannot
establish the contents of pretraining, or rule out every paraphrase.

The bulk run calls the app's existing `checked_draft` with triage enabled,
using Ollama Qwen2.5 1.5B Q4 and no cache, temperature zero, the client's
fixed seed and 8,192-token context, up to 384 generated tokens per request
and a 90-second request timeout. Model digest
`65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`.
Approval is then simulated through the existing approval function using an
explicit scripted reviewer. The strict policy accepts only the author's
semantic matches. The permissive policy accepts drafts as written if the
technical approval gates allow them. Both execute the unchanged checker.

From the repository root in an activated environment:

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
Invoke-WebRequest -UseBasicParsing 'https://auessaouira.ma/wp-content/uploads/2015/06/decret_81.pdf' -OutFile runs/accessibility-source.pdf
python -c "import pathlib,pymupdf; d=pymupdf.open('runs/accessibility-source.pdf'); pathlib.Path('runs/accessibility-source.txt').write_text(chr(12).join(p.get_text() for p in d),encoding='utf-8')"
ollama pull qwen2.5:1.5b
python scripts/real_interpreter_holdout.py . runs/accessibility-source.txt runs/holdout-leakage.json --audit
python scripts/real_interpreter_holdout.py . runs/accessibility-source.txt runs/holdout-drafts.jsonl --model qwen2.5:1.5b --max-tokens 384 --request-timeout 90 --triage
python scripts/score_interpreter_holdout.py . runs/accessibility-source.txt reports/morocco-interpreter-drafts.jsonl reports/morocco-interpreter-ratings.json runs/holdout-rescore.json
```

Use a fresh drafts path for a fresh run. The script skips completed IDs
when resuming a local output file. Semantic ratings are assigned explicitly
after inspecting the drafts. Labels were written by the benchmark author
with no independent review. Both samples are small.
The scoring command shown uses the published run and its ratings. If a new
run changes draft text or decisions, rate the new outputs before scoring.
