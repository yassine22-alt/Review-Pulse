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
  precision: 0.6806
  recall: 0.5294
  f1: 0.5956
wall_length_weighted:
  precision: 0.7107
  recall: 0.4408
  f1: 0.5441
wall_classifier_direct_per_primitive:
  precision: 0.7452
  recall: 0.8687
  f1: 0.8023
wall_classifier_direct_length_weighted:
  precision: 0.7032
  recall: 0.8125
  f1: 0.7539
door_instances:
  precision: 0.8695
  recall: 0.9294
  f1: 0.8984
  true: 439
  found: 408
  pred: 521
window_instances:
  precision: 0.7821
  recall: 0.6199
  f1: 0.6916
  true: 221
  found: 137
  pred: 179
```

## Worst items / misses

- (0.0, '0011-0041.svg', {'door': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 4, 'found': 1, 'pred': 2, 'correct': 2}, 'scale': 'user'})
- (0.0, '0029-0526.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0131-0227.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0140-0024.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0300-0017.svg', {'door': {'true': 16, 'found': 14, 'pred': 14, 'correct': 14}, 'window': {'true': 13, 'found': 6, 'pred': 7, 'correct': 6}, 'scale': 'user'})
- (0.0, '0696-0161.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0765-0089.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0899-0032.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '1027-0040.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '1074-0013.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
