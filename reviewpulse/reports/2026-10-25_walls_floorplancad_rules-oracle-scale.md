# Evaluation: walls_floorplancad

- dataset: floorplancad (public data only: no real plans scored yet)
- items: 100
- method: rules-oracle-scale
- oracle inputs: scale
- commit: 9b9a639
- date: 2026-10-25

## Metrics

```
split: test
files: 100
scale_mode: oracle
method: rules
wall_per_primitive:
  precision: 0.2484
  recall: 0.4310
  f1: 0.3151
wall_length_weighted:
  precision: 0.2274
  recall: 0.3752
  f1: 0.2832
door_instances:
  precision: 0.8627
  recall: 0.5308
  f1: 0.6572
  true: 439
  found: 233
  pred: 335
window_instances:
  precision: 0.7400
  recall: 0.1176
  f1: 0.2030
  true: 221
  found: 26
  pred: 50
```

## Worst items / misses

- (0.0, '0029-0526.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0131-0227.svg', {'door': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0140-0024.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0300-0017.svg', {'door': {'true': 16, 'found': 2, 'pred': 2, 'correct': 2}, 'window': {'true': 13, 'found': 3, 'pred': 6, 'correct': 6}, 'scale': 'user'})
- (0.0, '0346-0434.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0652-0058.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 1, 'correct': 0}, 'scale': 'user'})
- (0.0, '0696-0161.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0765-0089.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0899-0032.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '1027-0040.svg', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
