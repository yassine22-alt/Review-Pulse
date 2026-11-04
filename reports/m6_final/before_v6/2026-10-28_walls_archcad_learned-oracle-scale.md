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
  precision: 0.6798
  recall: 0.3977
  f1: 0.5018
wall_length_weighted:
  precision: 0.6798
  recall: 0.4238
  f1: 0.5221
wall_classifier_direct_per_primitive:
  precision: 0.7563
  recall: 0.6968
  f1: 0.7253
wall_classifier_direct_length_weighted:
  precision: 0.7615
  recall: 0.7716
  f1: 0.7665
door_instances:
  precision: 0.8889
  recall: 0.9270
  f1: 0.9075
  true: 178
  found: 165
  pred: 207
window_instances:
  precision: 0.5426
  recall: 0.3784
  f1: 0.4458
  true: 111
  found: 42
  pred: 94
```

## Worst items / misses

- (0.0, '33f6b678-6d08-4ea9-91e8-2cfc0868e9e0', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '35141919-8179-4089-a8f4-077e3c22e743', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '40e3affb-f891-41a1-96ac-d61340c1e5fa', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '424bb39f-bddb-4d84-9829-454bd680419d', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '509d03c0-8853-4aaa-9c1b-db0b51e03b73', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '5597a992-0f43-44e9-abcc-41d921795a85', {'door': {'true': 1, 'found': 1, 'pred': 1, 'correct': 1}, 'window': {'true': 1, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '58ed9246-92d3-46b3-9909-910916fa23d3', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '627133b6-ce40-4aaf-a995-ad6a5baa78d1', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.0, '71b51c89-9e12-4df4-9f5f-fc5d9af3d3be', {'door': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
- (0.01, '3f0b073f-c46e-494c-8c33-302da77152cf', {'door': {'true': 3, 'found': 2, 'pred': 2, 'correct': 2}, 'window': {'true': 0, 'found': 0, 'pred': 0, 'correct': 0}, 'scale': 'user'})
