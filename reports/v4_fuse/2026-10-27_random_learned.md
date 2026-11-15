# Evaluation: random

- dataset: synth (public data only: no real plans scored yet)
- items: 60
- method: learned
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-27

## Metrics

```
n: 60
format: dxf
walls:
  precision: 0.9920
  recall: 0.9994
  f1: 0.9957
door:
  precision: 0.9802
  recall: 0.9982
  f1: 0.9891
  tp: 545
  pred: 556
  true: 546
window:
  precision: 1.0000
  recall: 0.9968
  f1: 0.9984
  tp: 307
  pred: 307
  true: 308
opening:
  precision: 0.8333
  recall: 1.0000
  f1: 0.9091
  tp: 5
  pred: 6
  true: 5
rooms:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 474
  pred: 474
  true: 474
edges:
  precision: 0.9964
  recall: 1.0000
  f1: 0.9982
  tp: 551
  pred: 553
  true: 551
room_type_accuracy: 1.0000
min(room F1, edge F1) by style:
  door_style=arc_leaf: 1.0000
  door_style=arc_only: 0.9932
  door_style=block: 0.9966
  door_style=bulge: 1.0000
  door_style=segments: 1.0000
  scheme=aia: 0.9960
  scheme=fr: 1.0000
  scheme=none: 1.0000
  scheme=numeric: 0.9974
  units=m: 0.9983
  units=mm: 0.9985
  wall_style=filled: 1.0000
  wall_style=hatched: 0.9970
  wall_style=lines: 1.0000
  wall_style=polylines: 0.9963
```

## Worst items / misses

- (0.9523809523809523, 'rand_5049', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'block', 'angle': 0.0, 'units': 'm'}, {'door': (10, 11, 10), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (10, 11, 10)})
- (0.9523809523809523, 'rand_5058', {'scheme': 'numeric', 'wall_style': 'polylines', 'door_style': 'arc_only', 'angle': -11.4, 'units': 'mm'}, {'door': (9, 10, 10), 'window': (3, 3, 3), 'opening': (0, 1, 0), 'rooms': (7, 7, 7), 'edges': (10, 11, 10)})
- (0.9766511168746648, 'rand_5054', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 90.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (5, 5, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.981214486051893, 'rand_5038', {'scheme': 'aia', 'wall_style': 'filled', 'door_style': 'block', 'angle': -1.6, 'units': 'm'}, {'door': (8, 8, 8), 'window': (5, 5, 5), 'opening': (1, 1, 1), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9814187794202658, 'rand_5052', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 90.0, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9817942161469212, 'rand_5004', {'scheme': 'numeric', 'wall_style': 'hatched', 'door_style': 'bulge', 'angle': 0.0, 'units': 'm'}, {'door': (7, 8, 7), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (7, 7, 7), 'edges': (7, 7, 7)})
- (0.9821570629931193, 'rand_5035', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -13.0, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9836170609251057, 'rand_5020', {'scheme': 'none', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 0.0, 'units': 'm'}, {'door': (9, 9, 9), 'window': (5, 5, 5), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9853199345346683, 'rand_5059', {'scheme': 'numeric', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 90.0, 'units': 'mm'}, {'door': (8, 8, 8), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (7, 7, 7), 'edges': (8, 8, 8)})
- (0.9855814893587459, 'rand_5023', {'scheme': 'none', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 90.0, 'units': 'mm'}, {'door': (10, 10, 10), 'window': (6, 6, 6), 'opening': (1, 1, 1), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
