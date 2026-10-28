# Evaluation: walls_floorplancad

- dataset: floorplancad (public data only: no real plans scored yet)
- items: 100
- method: learned-oracle-scale
- oracle inputs: scale
- commit: 9b9a639
- date: 2026-10-28

## Metrics

```
split: test
scale_mode: oracle
files: 100
crashed: 0
method: rules+learned
wall_per_primitive:
  precision: 0.6790
  recall: 0.5201
  f1: 0.5890
wall_length_weighted:
  precision: 0.6773
  recall: 0.4350
  f1: 0.5297
wall_classifier_direct_per_primitive:
  precision: 0.6808
  recall: 0.9033
  f1: 0.7764
wall_classifier_direct_length_weighted:
  precision: 0.6571
  recall: 0.9119
  f1: 0.7638
door_instances:
  precision: 0.8700
  recall: 0.9294
  f1: 0.8987
  true: 439
  found: 408
  pred: 523
window_instances:
  precision: 0.7931
  recall: 0.8190
  f1: 0.8058
  true: 221
  found: 181
  pred: 232
```

## Worst items / misses

- (0.0, '0011-0041.svg', {'door': {'true': 1, 'found': 1, 'pred': 1, 'correct': 1}, 'window': {'true': 4, 'found': 1, 'pred': 1, 'correct': 1}, 'scale': 'user'})
- (0.0, '0029-0526.svg', {'door': {'true': 0, 'found': 0, 'pred': 2, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0087-0025.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0131-0227.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0140-0024.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0300-0017.svg', {'door': {'true': 16, 'found': 14, 'pred': 14, 'correct': 14}, 'window': {'true': 13, 'found': 9, 'pred': 11, 'correct': 10}, 'scale': 'user'})
- (0.0, '0696-0161.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0765-0089.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0899-0032.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '1027-0040.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
