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
  precision: 0.4855
  recall: 0.3678
  f1: 0.4185
wall_length_weighted:
  precision: 0.4713
  recall: 0.3956
  f1: 0.4302
wall_classifier_direct_per_primitive:
  precision: 0.4490
  recall: 0.5749
  f1: 0.5042
wall_classifier_direct_length_weighted:
  precision: 0.5529
  recall: 0.6378
  f1: 0.5923
door_instances:
  precision: 0.8703
  recall: 0.7978
  f1: 0.8324
  true: 178
  found: 142
  pred: 185
window_instances:
  precision: 0.5593
  recall: 0.5676
  f1: 0.5634
  true: 111
  found: 63
  pred: 118
```

## Worst items / misses

- (0.0, '070138dc-09a9-453f-810c-5b6d6e0d5982', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '0e915b3e-d61f-4219-8f6f-fb232e95ab69', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 3, 'found': 3, 'pred': 3, 'correct': 3}, 'scale': 'user'})
- (0.0, '33f6b678-6d08-4ea9-91e8-2cfc0868e9e0', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '35141919-8179-4089-a8f4-077e3c22e743', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '509d03c0-8853-4aaa-9c1b-db0b51e03b73', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '5597a992-0f43-44e9-abcc-41d921795a85', {'door': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '572fcd29-226a-4dc0-afab-fdecf7712016', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '5fa48b6e-2788-496f-b106-a8c747cefe6c', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '627133b6-ce40-4aaf-a995-ad6a5baa78d1', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '68095411-0fa0-4010-9d8b-87bef692ebc7', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
