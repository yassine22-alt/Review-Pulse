# ReviewPulse

**New here? Start with [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md): one command to set up,
one to check that everything works.**

Automated error detection on architectural plans, checked against a requirements document.
A plan goes in (vector PDF, DXF, DWG; scans next), an annotated PDF and an HTML report come out,
with every finding tied to its evidence on the drawing and to the clause it comes from.

This folder is the new implementation that follows the build plan (24 Oct 2026). The earlier
DeepFloorPlan experiment in the repository root is left untouched.

## Quickstart: the web app

```
pip install -e ".[app]"          # FastAPI service and web UI
ollama pull qwen2.5:7b           # optional: the local model that drafts rules from the requirements
rp serve                         # http://127.0.0.1:8000  (projects stored in data/app)
```

or, with Docker (the app and the drafting model in two containers):

```
docker compose up --build        # http://localhost:8000 ; first start downloads qwen2.5:7b (~4.7 GB)
```

In the app: create a project, drop the plan (PDF, DXF, SVG, PNG/JPG scan) and the requirement document
(PDF, DOCX, Markdown, text). The plan is analysed and checked against the base rule pack at once; the
document is split into clauses and each clause is drafted into a rule by the local model. The Rules tab
shows every clause next to its drafted rule: approve, edit or reject (approval runs the rule's self-test).
The Results tab shows the plan with each finding drawn on it, filters by verdict and severity, and lets
the reviewer confirm or reject detected elements and dismiss findings with a reason; every change re-runs
the check. Annotated PDF, HTML, CSV and JSON reports download from the same page.

`python scripts/demo.py` runs that whole flow through the HTTP API on a generated plan with planted
errors and prints what was found. The API is documented at `/docs` on a running server.

## How it works

### Compound regulation interpreter (opt-in)

`rp interpret demo runs/interpreter-demo` runs three compound examples offline. The new
`rp interpret` commands and `/api/interpreter` endpoints support source context, drafting,
independent semantic review, explicit approval, and deterministic checking with evidence traces.
They handle nested conditions, exemptions, quantifiers, aggregates, and filtered routes using the
existing building model. See [the interpreter guide](docs/regulation_interpreter.md) for the workflow,
input contract, tests, and current boundaries. Compound results are separate from the legacy Rules
tab and finding exports while those interfaces are migrated.

```
file ──R1──> sheets.json ──R2/R3──> sheet_<n>.json ──R5-R14──> building_<n>.json ──J1-J7──> findings + report
             (inspect)              (what was drawn)            (what it means)              (what is wrong)
                                                                        ▲
requirement document ──I3──> clauses ──I4──> draft rules ──I5 curator──> approved rule pack
```

| Folder | Role | Plan steps |
|---|---|---|
| `src/reviewpulse/ingest/` | file type and mode, PDF and DXF extraction | R1-R3 |
| `src/reviewpulse/core/` | ids, geometry, drawing-style normalisation, tiers | A1, R14 |
| `src/reviewpulse/annotate/` | text classes, scale, layout, dimensions, schedules | R5-R7, R11, R12 |
| `src/reviewpulse/perception/` | walls, openings, rooms and room graph | R8-R10 |
| `src/reviewpulse/rules/` | rule format, vocabulary, function registry, packs, rule tester | I1, I2, I5, I6 |
| `src/reviewpulse/engine/` | context, verdict policy, traversal / metric / consistency / swing checks | J1-J6 |
| `src/reviewpulse/report/` | annotated PDF, HTML report, CSV, debug images | J7 |
| `src/reviewpulse/eval/` | matching, metrics, oracle attribution, randomised generality test | E1-E4 |
| `src/reviewpulse/synth/` | synthetic plans with exact truth and planted errors | T1 |
| `src/reviewpulse/app/` | web service (FastAPI), background jobs, project store, single-page UI | product |
| `tests/` | unit, golden (end to end), generality | T2, T3 |
| `docs/` | decisions register, example requirement document, progress reports | |

## Install (Windows, PowerShell)

```
cd reviewpulse
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev,draw]"
pytest -q -m "not slow"
rp --help
```

## Use

```
rp check plan.pdf                         # whole pipeline with the starter rule pack
rp check plan.dxf --rules path/to/pack    # another pack
rp check runs/<id> --confirm <element_id> --dismiss <finding_id>:<reason>   # triage, logged in triage.json

rp inspect plan.pdf ; rp extract runs/<id> ; rp build runs/<id> ; rp check runs/<id>   # stage by stage
rp synth out/ --errors topo_exit_via_bath --errors metric_door_narrow           # test plans with truth
rp rules validate ; rp rules test                                                # rule pack checks
rp rules draft requirements.pdf ; rp rules review drafts/<doc>.drafts.yaml --pack <dir>   # LLM drafts, curator approves
rp eval drafting                                                                 # score the LLM on 30 gold clauses
rp eval random --n 60 ; rp eval findings --n 60 ; rp eval scale                  # evaluation reports
```

Outputs land in `runs/<id>/`: `sheet_0.json`, `building_0.json`, `scale_report_0.json`,
`rooms_0.png`, `findings.json`, `findings.csv`, `report.pdf`, `report.html`.

## Rule drafting with a local LLM (free)

Drafting uses an open-source model on your own machine, so nothing leaves it and nothing is billed:

```
winget install Ollama.Ollama        # or the installer from ollama.com
ollama pull qwen2.5:7b              # Apache-2.0, ~4.7 GB, fits a 6 GB GPU
rp rules draft docs/requirements_example.md
```

`--backend claude` switches to the hosted Claude API (needs `pip install -e ".[llm]"` and credentials).

## Scans and photos (raster path, optional)

`rp check plan.png` and scanned PDFs work without extras (rule-based walls, rooms, no OCR). For
the learned wall/door/window model and OCR:

```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126   # GPU build
pip install -e ".[raster]"
pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python scripts/prepare_cubicasa_seg.py ; python scripts/train_raster_seg.py       # model -> data/models/raster_seg
rp eval raster --n 100 --method all                                                # rules vs model vs fusion
```

Scans are never better than tier T2 (T3 without a readable dimension chain). The model is trained
on CubiCasa5K (CC BY-NC 4.0): non-commercial use only.

## Verdicts are honest

FAIL needs exact geometry (tier T1) or elements a user confirmed; a metric rule on an estimated
scale gives at most WARNING; a rule whose inputs are missing returns NOT_EVALUATED naming them.
Thresholds live in the rule pack and cite a clause of the uploaded document
(`docs/requirements_example.md` is a test fixture until the real regulation is supplied).

## Status

See `docs/progress/` for milestone reports with screenshots and numbers, `NOTES.md` for the
experiment log and `docs/DECISIONS.md` for the decisions register.

CI: `/.github/workflows/reviewpulse-ci.yml` (at the repository root) runs the linter, the fast
tests and `rp doctor` on every push and pull request.
