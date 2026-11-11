# Runbook: commands to run everything yourself

Everything below is PowerShell, run from the folder that contains your clone of the repository. Each block is
independent: copy one when you need it. Nothing here changes git history.

## 0. Open a terminal in the project, with the tools on

```powershell
cd <your clone of the repository>
.\.venv\Scripts\Activate.ps1          # created by .\setup.ps1
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
$env:REVIEWPULSE_LABEL_LLM = "0"        # tests and demos below do not need a model for labels
git status -sb                          # which branch you are on and what changed
```

## 1. Check that the whole project is healthy (about 3 minutes, no model needed)

```powershell
ruff check src tests                    # style: should say "All checks passed!"
pytest -q -m "not slow"                 # the exact command the GitHub CI runs
python -m reviewpulse.selfcheck         # a generated plan with planted errors, through the code and the web app
```

Every test of the closed loop (read a clause, approve, check, report) uses a scripted model, so it runs offline:

```powershell
pytest tests/app/test_closed_loop.py tests/unit/test_interpreter_findings.py tests/unit/test_relational.py tests/unit/test_domain_free.py -q
```

## 2. The local model that writes rules (Ollama)

```powershell
ollama list                             # must show qwen2.5:7b
ollama pull qwen2.5:7b                  # only if it is missing (4.7 GB, runs on the 6 GB GPU)
```

If `ollama list` fails, start the Ollama app from the Start menu, then run it again. The web app shows a green
"model" pill at the top right when the model is reachable.

## 3. Make the plans to test with (13 variants, each shows something different)

```powershell
python scripts/make_demo_plans.py demo_plans
explorer demo_plans
```

Open `demo_plans\README.md`: one line per scenario says what it shows and which findings must appear. Each scenario folder
has the plan as `.dxf` and as `.pdf`.

| Folder | What it shows |
|---|---|
| `01_clean` | no error: a warning until you confirm the inventory, then all satisfied |
| `02_door_too_narrow` | one door at 0.70 m against 0.80 m |
| `03_rooms_too_small` | small bedroom and living room, two conditions in one rule |
| `04_bedroom_through_bathroom` | a route rule |
| `05_garage_next_to_bedroom` | a direct link between two kinds of room |
| `06_dead_end_room` | a room with one door and no window |
| `07_exit_too_far` | travel distance over 15 m |
| `08_no_exit_at_all` | no door to the outside |
| `09_isolated_room` | a room with no door |
| `10_rotated_other_scale` | same error, page rotated 90 degrees at 1:50: the finding must not change |
| `11_everything_wrong` | measurements, a route, a dimension chain and a missing label together |
| `12_other_drawing_style` | another generator, French layers, millimetres, rotated 33 degrees |
| `13_l_shaped_clutter` | L-shaped plan with furniture and hatched walls |

## 4. The documents (requirements) to upload with a plan

| File | Use |
|---|---|
| `docs\requirements_example.md` | the English example document, 24 clauses |
| `docs\requirements_example_fr.md` | the same document in French (decimal commas, « m² », « au moins ») |

Both are test fixtures, not real regulations.

## 5. Start the web app and test it by hand

```powershell
python -m reviewpulse.cli serve         # leave this window open; stop it with Ctrl+C
```

In a second terminal (or just your browser) open **http://127.0.0.1:8000**.

Follow this order in the browser:

1. **New project**: give it a name, set your name as curator.
2. **Inputs** tab: upload a plan, for example `demo_plans\02_door_too_narrow\...dxf`, and wait for
   "Plan analysis" to finish. Then upload `docs\requirements_example.md`. The older drafter starts in the background; you
   do not need it, you can use the Requirements tab straight away.
3. **Requirements** tab:
   - click **Read all clauses** (about 15 minutes for 24 clauses with the local model) or **Read this clause** on one
     clause. Rules appear one by one while it reads. A clause that cannot be turned into a checked rule says why.
   - on a clause with a rule: **Second reader**, then type your reviewer name, tick "I read the second reader's notes" if
     it shows any, then **Approve** (or **Reject**).
   - **Confirm** the plan inventory at the top. Until you do, a rule can show a violation but never a pass.
4. Click **Run check** (top right). Approved rules run with no model.
5. **Results** tab: violations are drawn on the plan with the measured value and the limit. **Coverage report** opens a
   printable page that accounts for every clause.

To try another scenario, create a new project (do not reuse one: approvals belong to the project).

## 6. Run the whole flow from the command line instead (with the real model)

With the server running (section 5), in another terminal. It reads the clauses of an existing project, approves them under
your name, runs the check and prints the findings and the coverage:

```powershell
python scripts/closed_loop_demo.py <project id> "Khaoula"
```

The project id is the 12-character code in the browser address `.../#/p/<project id>/...`. The coverage page is saved to
`reports\extractor_eval\coverage_demo.html`.

Measurements against planted errors (each takes 10 to 30 minutes, run them when you do not need the GPU):

```powershell
python -u scripts/closed_loop_eval.py 10               # thresholds: door width, bedroom and living room size
python -u scripts/closed_loop_eval_relational.py 10    # routes, links, door counts, travel distance
python scripts/stairs_synth.py 200                     # stair finder against known truth
python scripts/stairs_eval.py 150                      # stair finder against FloorPlanCAD labels
```

## 7. Stop and clean up

```powershell
# stop the app: Ctrl+C in the window that runs it. If the window is gone:
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Projects you created live in `data\app\` (not in git). Deleting a project folder there removes it.

## 8. Put your work on GitHub

```powershell
git fetch origin
git status -sb                          # check that you are not "behind"
git add <the files you changed>
git commit -m "your message"
git push
```

If `git status -sb` says `behind`, someone pushed first: run `git rebase origin/rule-interpreter`, then
`ruff check src tests` and `pytest -q -m "not slow"` again before you push.

## Where to read more

- what each milestone built and measured: `docs\progress\M7_*.md`, `M8_*.md`
- the facts format: `docs\fact_graph.md`
- decisions and their evidence: `docs\DECISIONS.md` (A52 onward)
