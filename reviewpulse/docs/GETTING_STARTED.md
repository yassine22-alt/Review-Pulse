# Getting started with ReviewPulse

I wrote this so you can set up ReviewPulse, see it work, and start changing it, without reading
anything else first. Everything below has been run on a fresh copy of the repository.

## What ReviewPulse does

You give it a floor plan (PDF, DXF, SVG, or a scan) and a requirements document. It finds the
walls, doors, windows and rooms on the plan, checks them against rules taken from the document,
and gives back a report with every problem drawn on the plan and linked to the clause it breaks.

Some examples of what it checks: a door that is too narrow, a room that is too small, an escape
route that is too long or goes through a bathroom, a missing room from the client's brief, a door
tag that does not match the schedule.

It never fails a plan on a guess. If the scale was estimated, a room type was guessed, or text
was read by OCR, the result is a warning that asks a person to look, not a failure.

## 1. Set it up (one command)

You need Python 3.11 or 3.12 (python.org) and git.

**Windows (PowerShell):**

```
cd reviewpulse
.\setup.ps1
```

**Mac or Linux:**

```
cd reviewpulse
./setup.sh
```

This creates a `.venv` folder, installs everything into it, and then runs a self-check. The
self-check prints one line per part, and ends with "All required parts work." when you are ready:

```
1. Installation
[ ok ] Python 3.11
[ ok ] required packages (17)
[ ok ] web app (rp serve)
[ -- ] scanned plans: wall/door/window model: see README, "Scans"
...
2. Pipeline (a generated plan with planted errors)
[ ok ] check a DXF plan: 3/3 planted errors found, reports written, 2 s
[ ok ] check a PDF plan: 3/3 planted errors found, reports written, 1 s
3. Web app
[ ok ] web app: page served, plan uploaded and checked through the API, 3/3 planted errors found
```

`[ ok ]` works, `[ -- ]` is optional and not installed (the line says how to add it), `[FAIL]` is
broken. You can run the self-check again at any time:

```
rp doctor
```

Three things are optional:

| Optional part | What it adds | How to get it |
|---|---|---|
| Scanned plans | reading scans and photos (a neural network for walls, plus OCR for text) | `.\setup.ps1 -Scans` or `./setup.sh --scans`, then ask me for the scan model folder and put it in `data/models/raster_seg` |
| Rule-drafting model | turning a requirements document into draft rules | install Ollama (ollama.com), then `ollama pull qwen2.5:7b` |
| Trained model for CAD drawings | much better walls, doors and windows on real CAD drawings | ask me for the model folder and put it in `data/models/primitive_lgbm` |

The trained models are not in the repository: they are large, and they learn from datasets that
allow non-commercial use only, so I share them directly. Without the trained model, CAD drawings
are read with the geometric rules only. That works well
on clean drawings and is how the tests run.

## 2. Use the app

```
.\.venv\Scripts\Activate.ps1      (Mac/Linux: source .venv/bin/activate)
rp serve
```

Open http://127.0.0.1:8000. Create a project, drop in a plan, and it is analysed and checked
straight away against the starter rules. Drop in a requirements document and each clause is
drafted into a rule; you approve, edit or reject each one. The Results tab shows the findings on
the plan, and the reports download from there (annotated PDF, HTML, CSV, JSON).

To see the whole flow without clicking: `python scripts/demo.py`.

## 3. Use the command line

```
rp check plan.pdf                          check a plan with the starter rules
rp check plan.pdf --brief programme.xlsx   also check it against the client's room programme
rp synth out/ --errors metric_door_narrow  make a test plan with a known mistake in it
rp rules validate                          check the rule files are well formed
```

Results go to `runs/<id>/`: `report.pdf` and `report.html` are the ones to open.

## 4. How the code is organised

A plan goes through these steps, in this order. Each step has its own folder in
`src/reviewpulse/`:

| Step | Folder | What it does |
|---|---|---|
| Read the file | `ingest/` | opens PDF, DXF, SVG and images, and pulls out lines, arcs and text |
| Clean up | `core/`, `annotate/` | finds the scale, sorts the text (labels, dimensions, tags), recognises drawing styles |
| Understand | `perception/` | builds walls, doors, windows and rooms from the lines |
| Learned pass | `perception/learned/` | a trained classifier that tells walls from furniture and hatching on real CAD drawings |
| Check | `rules/`, `engine/` | rules written in YAML, and the code that applies them |
| Report | `report/` | the annotated PDF and the HTML report |
| App | `app/` | the web server and the page |
| Test data | `synth/` | generates plans with known answers and planted mistakes |
| Measure | `eval/` | scores each step against known answers |

The whole flow is in one file, `src/reviewpulse/pipeline.py`. Start reading there.

## 5. Add or change a rule

Rules are YAML files in `src/reviewpulse/rules/packs/starter/`. Each one says what it checks,
the threshold, and which clause of the requirements document it comes from. Copy an existing rule
(for example `C-D3.yaml`, minimum bedroom area), change it, then:

```
rp rules validate        is the file well formed?
rp rules test            does the rule pass on a correct plan and fail on a planted mistake?
```

## 6. Run the tests

```
pytest -q -m "not slow"      about 3 minutes, about 280 tests
rp doctor
```

A few tests are skipped when the trained model or a public dataset is not on your machine; that
is expected (`pytest -rs` says why each one was skipped). `pytest -q` without `-m "not slow"` also
runs the slow ones (about 7 minutes).

Every change should keep both green. GitHub runs them on every push.

## 7. Where to read more

- `docs/DECISIONS.md`: every design decision, and the measurement behind it.
- `docs/progress/`: one report per milestone, with pictures and numbers.
- `docs/check_inventory.md`: what reviewers check on real projects, and which of it we cover.
- `NOTES.md`: the detailed log of experiments.

## 8. What is still open

- **Real projects.** Everything so far is measured on public datasets and generated plans. Real
  projects with their reviewers' comments are the most useful thing we can get.
- **Which regulation.** The rules follow an example requirements document. We need to choose the
  country and building types so the rules match the regulation that actually applies.
- **Licences.** The trained models learn from datasets that allow non-commercial use only.
  Commercial use needs training on data we are allowed to use, such as our own plans.
