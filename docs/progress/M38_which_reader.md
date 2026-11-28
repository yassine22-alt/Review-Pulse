# M38: which reader read the drawing

Written 28 November 2026.

## What I found

ReviewPulse reads CAD drawings with hand written rules and, when it is installed, a trained model on top of them. The model is
not in the repository (see below). **The working copy I had been developing in did not have it**, so what was run there used the
rules only. `rp doctor` marked the model as optional, all required checks passed, and the web app said nothing. My requirements
page ([M34](M34_requirements_traceability.md)) also quoted the rules-only scores as the project's accuracy on real drawings.

Results from that copy that depend on which walls, doors, windows or rooms were read were made with the rules only. The text
searches over notes and labels do not use this reader.

## Measured again, both ways, with the same code

100 drawings of the FloorPlanCAD test split, code at commit `6d35636`, no drawing crashed. The drawing's true scale is given to
both (`oracle scale`), so scale reading is not tested here. Walls are scored by length; doors and windows one object at a time.

| | Rules only: precision / recall / F1 | With the trained model: precision / recall / F1 |
| --- | --- | --- |
| Walls | 0.23 / 0.38 / **0.28** | 0.68 / 0.44 / **0.53** |
| Doors (439) | 0.88 / 0.66 / **0.75** | 0.87 / 0.93 / **0.90** |
| Windows (221) | 0.74 / 0.12 / **0.20** | 0.80 / 0.82 / **0.81** |

    python -m reviewpulse.cli eval walls --dataset floorplancad --n 100 --method learned   (and --method rules)

* One small loss: door precision is about one point lower with the model.
* **Walls remain weak.** With the model, less than half of the wall length is found in the final reading. The model's own line by
  line answers, before walls are assembled from them, reach recall 0.91 and F1 0.76, so much is lost in the assembly step.
* These agree with what was measured when the model was made ([M6](M6_evidence_and_measurement.md)).
* One public dataset. It is not evidence about any particular office's drawings.

## What changed in the app

* Every sheet records how it was read: with the trained model (and the first 12 characters of the SHA-256 of the model file),
  with the rules only, with the rules because the model found no walls, or from a scan.
* "What was read" says it in words.
* If a sheet was read without the model, the review desk shows a warning on every tab, saying that checks which count or measure
  doors and windows can miss many of them.
* `/api/health` reports the installed model's fingerprint.

Drawings uploaded before this change have no record until they are uploaded again. Only this model's version is recorded per
sheet; the versions of the other models are not (NFR-07 stays partial).

## Using the model, and its licence

Unzip `ReviewPulse_models.zip` in the repository root and check that `rp doctor` shows `[ ok ]` for "trained model for CAD
drawings" ([getting started](../GETTING_STARTED.md)). The model learned from datasets that allow **non-commercial use only**, so
a commercial product would need a model trained on other data.
