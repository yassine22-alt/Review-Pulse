# Evaluation: walls_archcad

- dataset: archcad (public data only: no real plans scored yet)
- items: 100
- method: learned-oracle-scale
- oracle inputs: scale
- commit: 9b9a639
- date: 2026-10-28

## Metrics

```
split: test
scale_mode: oracle
selection: slices with walls
files: 100
crashed: 0
method: rules+learned
wall_per_primitive:
  precision: 0.4749
  recall: 0.3522
  f1: 0.4045
wall_length_weighted:
  precision: 0.4534
  recall: 0.3640
  f1: 0.4038
wall_classifier_direct_per_primitive:
  precision: 0.4490
  recall: 0.5749
  f1: 0.5042
wall_classifier_direct_length_weighted:
  precision: 0.5529
  recall: 0.6378
  f1: 0.5923
door_instances:
  precision: 0.8696
  recall: 0.7978
  f1: 0.8321
  true: 178
  found: 142
  pred: 184
window_instances:
  precision: 0.5495
  recall: 0.4234
  f1: 0.4783
  true: 111
  found: 47
  pred: 91
```

## Worst items / misses

- (0.0, '070138dc-09a9-453f-810c-5b6d6e0d5982', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0e915b3e-d61f-4219-8f6f-fb232e95ab69', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 3, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '33f6b678-6d08-4ea9-91e8-2cfc0868e9e0', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '35141919-8179-4089-a8f4-077e3c22e743', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '35dbf1a3-8ab3-4772-90ba-9dd9079d7b8a', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '509d03c0-8853-4aaa-9c1b-db0b51e03b73', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '551557d5-c645-47a4-874c-08017098c6c9', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '5597a992-0f43-44e9-abcc-41d921795a85', {'door': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '572fcd29-226a-4dc0-afab-fdecf7712016', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '627133b6-ce40-4aaf-a995-ad6a5baa78d1', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
