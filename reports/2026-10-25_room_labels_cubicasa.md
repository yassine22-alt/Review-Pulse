# Evaluation: room labels -> room type

- dataset: CubiCasa5K test split ground-truth labels (3701 labelled spaces with a room type; lexicon mined from train+val only)

## Metrics

| variant | recognised | correct | precision |
|---|---|---|---|
| baseline_fr_en | 0.065 | 0.065 | 1.000 |
| curated | 0.856 | 0.856 | 1.000 |
| curated+mined | 1.000 | 1.000 | 1.000 |
| curated+mined+llm | 1.000 | 1.000 | 1.000 |
| llm_only | 0.867 | 0.593 | 0.683 |

## Most frequent misses (shipped lexicon)

- ULK.VÄL.VAR -> none (truth storage) x1
- PUKUHUONE -> none (truth storage) x1
