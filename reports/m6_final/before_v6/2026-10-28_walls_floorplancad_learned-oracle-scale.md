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
  precision: 0.6207
  recall: 0.5300
  f1: 0.5717
wall_length_weighted:
  precision: 0.6421
  recall: 0.4453
  f1: 0.5259
wall_classifier_direct_per_primitive:
  precision: 0.6808
  recall: 0.9033
  f1: 0.7764
wall_classifier_direct_length_weighted:
  precision: 0.6571
  recall: 0.9119
  f1: 0.7638
door_instances:
  precision: 0.8707
  recall: 0.9317
  f1: 0.9002
  true: 439
  found: 409
  pred: 526
window_instances:
  precision: 0.7879
  recall: 0.5882
  f1: 0.6736
  true: 221
  found: 130
  pred: 165
```

## Worst items / misses

- (0.0, '0011-0041.svg', {'door': {'true': 1, 'found': 1, 'pred': 1, 'correct': 1}, 'window': {'true': 4, 'found': 1, 'pred': 1, 'correct': 1}, 'scale': 'user'})
- (0.0, '0029-0526.svg', {'door': {'true': 0, 'found': 0, 'pred': 2, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0087-0025.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0131-0227.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0140-0024.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0300-0017.svg', {'door': {'true': 16, 'found': 14, 'pred': 14, 'correct': 14}, 'window': {'true': 13, 'found': 5, 'pred': 7, 'correct': 6}, 'scale': 'user'})
- (0.0, '0696-0161.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0765-0089.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0899-0032.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '1027-0040.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
