# Input formats

Task B1. What each supported input preserves, how ReviewPulse reads it, and what happens when the input
is weaker than expected. Code: `ingest/classify.py` (type and page mode), `pipeline.extract_stub`
(reader dispatch), `pipeline.build_model` (vector or raster interpretation), `core/tiers.py` (tier).
Measured accuracy per item and input: [extraction_catalogue.md](extraction_catalogue.md). End-to-end
runs of every input type: the latest `reports/*_acceptance.md` (`python scripts/acceptance.py`).

## 1. Detection

The type comes from the file's magic bytes first and its extension second, so a renamed file is still
read correctly:

| bytes / extension | type |
|---|---|
| `%PDF` | pdf |
| `AC10…` | dwg |
| PNG, JPEG, TIFF signatures; `.bmp` | image |
| `<svg` in the first 2 kB, or `.svg` | svg |
| `SECTION` in the header, or `.dxf` | dxf |

Errors stop with one line and exit code 2 (`IngestError`): missing file, `.pdf` without a PDF header,
encrypted PDF, zero pages, unreadable image, unsupported type.

Each PDF page is then classified by its content:

| page mode | condition | read as |
|---|---|---|
| vector | at least 200 path items and images cover < 50 % of the page | vector path |
| raster | images cover at least 80 % and fewer than 50 path items | raster path (scan) |
| mixed | anything else | vector path (see limits, §4) |

## 2. What each format preserves

| | DXF / DWG | vector PDF | SVG | scanned PDF, PNG, JPG, TIFF |
|---|---|---|---|---|
| geometry | exact, drawing units | exact, paper mm | exact, paper mm | pixels, vectorised from model masks |
| arcs | true arcs (OCS handled for mirrored blocks) | Bézier curves, refitted to arcs | path arcs and Béziers, refitted | from the mask |
| layers | yes | optional-content groups, when present | groups / classes, when present | no |
| blocks (door, window symbols) | yes, with insert handles | no (flattened) | no | no |
| text | yes, with height and rotation | yes, unless converted to outlines | yes | OCR (PaddleOCR, 4 orientations) |
| dimensions | DIMENSION entities with true measurement | text + drawn graphics, re-associated | text + graphics | OCR text + detected line segments |
| scale | `$INSUNITS` (exact) | dimension consensus, else a door-size prior | dimension consensus, else a door-size prior | dimension consensus on OCR, else a wall-thickness prior |
| best tier | T1 | T1 (verified scale) | T1 (verified scale) | T2 (verified scale), else T3 |

The tier rules (`core/tiers.py`): **T1** = vector page with DXF units or a dimension consensus at
confidence ≥ 0.8; **T2** = a verified scale on any other page; **T3** = estimated scale. A FAIL needs T1
or user-confirmed deciding elements (engine/policy.py). Anything weaker returns WARNING with the reason,
and metric rules without any scale return NOT_EVALUATED.

## 3. Fallback behaviour

| situation | what happens | effect on verdicts |
|---|---|---|
| no scale on a vector page | door-symbol scale prior (`symbol_prior`) | T3: metric findings at most WARNING |
| no readable dimensions on a scan | wall-thickness prior (dominant wall = 0.20 m) | T3 |
| image without dpi metadata | 300 dpi assumed, warning recorded | page size only; scale is still found from the drawing |
| DXF with an empty model space | warning recorded, empty model | rules NOT_EVALUATED |
| room labels in another language | multilingual lexicon, then the local LLM (marked lower confidence) | presence rules on OCR'd input stay WARNING below T1 |
| a trained model is absent | rules-only perception (learned pass skipped) | lower accuracy on real drawings, same contract |
| Ollama not running | rule drafting unavailable; approved rule packs still run | none on checking |

## 4. Known limits (open)

1. **Mixed PDF pages** go through the vector path only. A vector plan over a scanned background, or a
   scan with vector annotations, loses its raster content, and the page can never reach T1 (the tier
   requires mode `vector`).
2. **Text converted to outlines** in vector PDFs is detected (`text_as_outlines` warning), but the page
   is not yet sent to OCR. Labels and dimensions are then missing, and the scale falls back to the prior.
3. **DWG** is read through the ODA File Converter (`ezdxf.addons.odafc`). It is not installed in this
   environment, and DWG has not been tested end to end.
4. **Several sheets in one PDF**: each page becomes its own model. Pages are not yet classified by sheet
   type (plan, schedule, section), and schedules on a separate page are not joined to the plan.
5. **Scans** are licensed as non-commercial: the segmentation model is trained on CubiCasa5K
   (CC BY-NC 4.0). The vector primitive classifier is trained on FloorPlanCAD (CC BY-NC 4.0).
