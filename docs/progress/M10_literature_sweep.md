# What the literature says about our open problems (November 2026)

This page records a broad search done while the real-world tests were running. It is a map of methods we can use, with what each
would change for ReviewPulse. We read abstracts and excerpts, not every paper in full, so each item says what it is based on.
Nothing here is adopted until we measure it on our own annotation-free tests (see `M10_real_world_findings.md`).

## The six general problems

1. Reading rooms and walls from drawings that differ in style (CAD vector, PDF export, scan), with missing walls and symbols.
2. Turning regulation text into rules a program can check, when clauses are conditional, compound or refer to other clauses.
3. Reading long, messy documents (tables, multi-page prose, references).
4. Knowing when a model's answer is valid but wrong, and abstaining.
5. Scale and units across metric and imperial drawings.
6. Using vision-language models on plans, as an independent second reader.

## What we found, by problem

### 1. Rooms and walls

- Current learned methods work on raster images (RoomFormer, Raster2Seq 2026, CAGE, multibranch segmentation 2025). They are
  trained on CubiCasa5K and R2V, whose labels are known to be inconsistent and whose drawing styles differ. A 2024 thesis on
  CubiCasa5K found the three styles behave differently and that more training data does not always help.
- For vector CAD, SymPoint (ICLR 2024) treats drawing primitives as points and beats the previous best (GAT-CADNet) by 9.6 PQ on
  FloorPlanCAD. It spots walls, doors and windows from the primitives themselves.
- A survey and a multimodal segmentation paper both report that using the text on the plan (room labels) improves room
  segmentation. This is the idea behind our label-seeded split.
- Use for us: label-seeded flooding is supported by the literature as a cheap, style-independent signal. A learned wall or
  symbol detector (SymPoint on vectors, a Raster2Seq-class model on scans) is the route to scans and sketches, which we cannot
  read today. It needs a GPU setup and measurement before we depend on it.

### 2. Regulation text to rules

- LLM-FuncMapper (Tsinghua) matches each clause to one of 66 atomic functions and composes them; it beat fine-tuning by 19% in
  function matching. This is close to our design (a catalogue of facts the model chooses from).
- A 2026 study found an LLM was perfect on single-parameter checks but only 20 to 60% right on spatial rules, and worse on
  nested conditions. This matches what we see.
- A 2026 human-in-the-loop system (RASE: requirement, applicability, selection, exception) found its model failed on clauses
  with several exceptions and cut conditions out of exemptions. Their conclusion is the same as ours: a person approves.
- Use for us: keep the model choosing among named building blocks; add more topological blocks; keep approval mandatory.

### 3. Long documents

- Docling (IBM, MIT licence) and MinerU parse layout and tables with trained models. MinerU keeps nested table headers (as
  HTML); Docling has a cleaner document model. A benchmark (READoc) shows most parsers recover page-level layout but not the
  document-wide heading hierarchy, which is what we need.
- StrucChunk (structure-aware retrieval for legal text) treats a document as a graph of provisions and resolves cross-references
  before use. Our own real-document study shows the same need: many ADA clauses only say "shall comply with 307".
- Use for us: resolve references by bringing the referenced clause into the context. Try Docling or MinerU for table pages our
  reader skips when its time budget runs out, and compare on the same documents.

### 4. Valid but wrong answers

- Roundtrip verification (2026): write the rule, describe it back in words, formalise the description again, and check that the
  two rules are equivalent. Rules that fail the equivalence check drift 1.4 to 2.5 times more from the source meaning. It is a
  heuristic, not a proof.
- Semantic entropy (Nature 2024): sample several answers and group them by meaning; spread across meanings signals invention.
  Our rules have an exact notion of meaning: behaviour on generated plans.
- Conformal risk control (2026) can certify outputs only if the base error is below the target, and it broke on 14 of 16
  cross-dataset transfers. We must not promise a guarantee across domains; a monitored abstention rate is the honest version.
- Grammar-constrained decoding guarantees syntax but can distort what the model prefers (NeurIPS 2024). Our compile and sentence
  checks already catch syntax; the unsolved part is meaning.

### 5. Scale

- The search found nothing specific about recovering scale from dimension text in drawings. Our approach (written scale plus
  agreeing dimensions, refuse when they scatter) has no outside confirmation; it is justified only by our own tests.

### 6. Vision-language models

- AECV-Bench (2026): models read text on drawings well (up to 0.95) but count doors and windows poorly (0.40 to 0.55).
  Zero-shot room area from images with 8B models is weak. HouseMind (CVPR 2026) shows models do much better when the plan is
  given as structured data. FloorplanQA says the same.
- Use for us: keep the vision model for naming sheets and reading text, never for measuring or counting. Give models the fact
  graph, not the picture. This confirms our earlier choice.

## What we will try, in order

1. **Roundtrip check with exact comparison.** Re-formalise the readback independently and compare the two rules by behaviour on
   generated plans. This replaces the noisy second reader with a deterministic comparison.
2. **Reference resolution.** When a clause says it must comply with another clause, bring that clause into what is read.
3. **Meaning-level agreement.** Draft several times and cluster by behaviour; abstain when no cluster dominates.
4. **Table pages.** Measure Docling or MinerU against our reader on the table pages we skip.
5. **Learned wall and symbol detection** for vectors (SymPoint) and for scans, as an optional stage behind a clear switch.

Each is adopted only if its gain clearly outweighs its losses on our tests, and the losses are recorded here.
