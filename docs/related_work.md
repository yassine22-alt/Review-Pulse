# Recent work and what ReviewPulse takes from it

27 October 2026. Searched: vector symbol spotting, room extraction, compliance checking with
language models, and benchmarks of AI on drawings. Kept only what changes a decision for us.

## What the field confirms about our design

- **Language and vision models read the text on drawings well and the drawing itself badly.**
  AECV-Bench (2026, 120 plans) finds models read printed text nearly perfectly but struggle with the
  symbols next to it ([paper](https://arxiv.org/abs/2601.04819),
  [write-up](https://www.aecfoundry.com/blog/can-ai-really-read-your-building-plans-aecv-bench-gets-a-major-upgrade)).
  CrossProjection (2026) measures line-endpoint localisation at 22% for the best model and 0-4% for
  open models ([paper](https://arxiv.org/html/2608.00473v1)). This supports keeping geometry in our
  own measured pipeline and using the language model only for text (labels, clauses), never for
  measuring or judging.
- **Compliance research converges on our three-part architecture.** Rules are drafted from text by a
  language model, the drawing becomes a graph of elements and rooms, and an engine runs the rules
  on it ([RMIT framework, 2026](https://arxiv.org/pdf/2607.00015);
  [LLM checking in BIM, 2026](https://www.sciencedirect.com/science/article/pii/S0926580525007472)).
  Some systems let the model write executable code and repair it when it fails
  ([arXiv 2506.20551](https://arxiv.org/pdf/2506.20551)). We keep model output to a small checked
  frame mapped onto audited functions, so every rule is reviewable and nothing generated runs
  unseen.
- **Layer names cannot be relied on.** CADSpotting points out that methods using CAD layer
  information break where layers are inconsistent or missing
  ([paper](https://arxiv.org/html/2412.07377)). The same holds for us. The current training run adds
  ArchCAD, whose drawings have no layers or colours, for exactly this reason.

## What we can use

| Item | What it is | Licence | Use for ReviewPulse |
|---|---|---|---|
| [CODE-ACCORD](https://arxiv.org/pdf/2403.02231v3) | 862 regulation sentences (England, Finland) with 4,297 entities and 4,329 relations, annotated by 12 people | CC BY 4.0 (per a repository record; confirm on GitHub) | A real benchmark for our clause drafting, which today is measured on 30 gold clauses only. Commercial use allowed |
| Text as a primitive ([Text-Enhanced Symbol Spotting, 2025](https://arxiv.org/pdf/2510.11091); [TextCAD, 2026](https://arxiv.org/pdf/2607.12678)) | Text items become graph nodes beside lines and arcs; reported state of the art on FloorPlanCAD with text | Papers | Cheap to adopt: add "text nearby" features (tag, room label, dimension) to our classifier. Our pipeline already classifies every text item |
| Local vision-language models (Qwen2.5-VL family, open weights, runs in Ollama) | Read text in images, including rotated and handwritten | Apache-2.0 (most sizes) | Re-read room labels on scans, where our OCR gets 53% of labels right. Text only, never geometry, by the finding above |
| [VectorFloorSeg](https://openaccess.thecvf.com/content/CVPR2023/papers/Yang_VectorFloorSeg_Two-Stream_Graph_Attention_Network_for_Vectorized_Roughcast_Floorplan_Segmentation_CVPR_2023_paper.pdf) (CVPR 2023, code on GitHub) | Rooms from vector lines with a graph network | Check repository | A second opinion on room closure where detected walls leave gaps (our gap on real CAD) |
| [VF-GraphSAGE](https://zenodo.org/records/23455124) (2026) | Room type from the room graph, code and weights | MIT | Suggest a type for unlabelled rooms, as a WARNING-level hint only. Today such rooms make type rules NOT_EVALUATED |
| [DPSS](https://arxiv.org/pdf/2503.22346) (ArchCAD authors, NeurIPS 2025) | Image and primitive branches fused, transformer decoder; state of the art on FloorPlanCAD and ArchCAD | Code released, licence not stated; weights trained on non-commercial data | Benchmark reference only for now: GPU-heavy, licence unclear |
| [CADSpotting](https://arxiv.org/html/2412.07377) | 87.4 PQ on FloorPlanCAD; sliding windows for large drawings; LS-CAD dataset of about 1,000 m2 per drawing | No code or licence found | Insight: real sheets are about 10 times larger than FloorPlanCAD tiles. We must test whole sheets, not only tiles |

## What changes in our plan

1. Evaluate clause drafting on CODE-ACCORD (after confirming its licence).
2. Add text-neighbourhood features to the primitive classifier at the next retraining.
3. Test a local vision-language model as a second reader for room labels on scans, measured on the
   same 20 scans (53% today).
4. Measure on whole real sheets, not only 14 m tiles, for both accuracy and run time.
5. Keep DPSS and CADSpotting as reference numbers. Neither is adopted while their code licence is
   unknown and their weights are trained on non-commercial data.

Not found: any public dataset of reviewer comments or real compliance errors on plans. The team's
own review comment sheets remain the only source of "errors that matter" (see
[check_inventory.md](check_inventory.md)).
