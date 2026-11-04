# Data licences

Raw data lives outside git (`data/raw/`, `data/processed/`). Record every dataset here
before using it: licence, URL, date fetched and sha256 of the archive.

| Dataset | Licence | URL | Fetched | sha256 | Notes |
|---|---|---|---|---|---|
| Synthetic plans (`reviewpulse.synth`) | ours | generated | - | - | Exact truth; the main regression set |
| FloorPlanCAD | annotations CC BY-NC 4.0 (drawings not owned by the authors) | floorplancad.github.io / VecFormer README mirror | not yet | | Non-commercial |
| ResPlan | data CC BY 4.0, code MIT | github.com/m-agour/ResPlan | not yet | | Oracle input for R10 |
| CubiCasa5K | non-commercial (check repo LICENSE) | zenodo.org/record/2613548 | not yet | | Raster path R13 |
| ArchCAD 40K | CC BY-NC 4.0, gated (non-commercial use confirmed in the access form) | huggingface.co/datasets/jackluoluo/ArchCAD | 2026-10-27, `data/json.zip` + `data/svg.zip` (png/point/caption not fetched) | json 156c27425a38141a..., svg 7414169ffecbc462... | 41,097 slices of 14 x 14 m; no official split (hash split in eval/adapters/archcad.py); HF_TOKEN in .env |
| CODE-ACCORD v1.0.0 | CC BY 4.0 (Zenodo record) | doi.org/10.5281/zenodo.10210022 | 2026-10-27, full archive (annotated_data extracted) | zip f75b2a86d7cd953f... | 862 regulation sentences (England, Finland), entities and relations by 12 annotators; drafting benchmark (scripts/eval_drafting_code_accord.py). Commercial use allowed |
| CVC-FP | check site | dag.cvc.uab.es/DATASETS/CVC-FP.zip | not yet | | 122 scans |
| FP-TXT | annotations MIT | zenodo.org/records/7921780 | not yet | | Text boxes |

Code licence note: PyMuPDF is AGPL-3.0 (decision D2) - fine for coursework, to revisit before
the tool is shared outside the team.

## Fetched

| Dataset | Licence | Source | Fetched | sha256 (first file) |
|---|---|---|---|---|
| floorplancad | annotations CC BY-NC 4.0; drawings not owned by the authors (non-commercial) | https://floorplancad.github.io/ (single-zip mirror from the VecFormer README) | 2026-10-24 | `f05ad26ea31f6c0e...` |
| resplan | data CC BY 4.0, code MIT | https://github.com/m-agour/ResPlan | 2026-10-24 | `f718de8865e51bbe...` |
| fptxt | annotations MIT (images from CubiCasa5K / CVC-FP keep their own licences) | https://zenodo.org/records/7921780 | 2026-10-24 | `0afe36ff0a37faca...` |
| cubicasa5k | CC BY-NC 4.0 (non-commercial; check the repository LICENSE) | https://zenodo.org/records/2613548 | 2026-10-24 | `a4a3398534d6abb7...` |

## Model weights fetched by hand

| Weights | Licence | Source | Fetched | sha256 | Used for |
|---|---|---|---|---|---|
| DeepFloorPlan TF2 SavedModel (VGG16, `model.zip`, 107 MB) | GPL-3.0 (repository licence; trained on R3D) | TF2DeepFloorplan README, `gdown https://drive.google.com/uc?id=1tuqUPbiZnuubPFHMQqCo1_kFNKq4hU8i` (github.com/zcemycl/TF2DeepFloorplan) | 2026-10-26 | `7791f0d4bc4c0137...` | Baseline 0 only: running the original repo pipeline (docs/baseline_0.md); not used by ReviewPulse |
| DeepFloorPlan TF2 TFLite (`tflite.zip`, 37 MB) | GPL-3.0 | same README, `...uc?id=1B-Fw-zgufEqiLm00ec2WCMUo5E6RY2eO` | 2026-10-26 | `256cdaf770709b59...` | not used (kept for the original's TFLite option) |
