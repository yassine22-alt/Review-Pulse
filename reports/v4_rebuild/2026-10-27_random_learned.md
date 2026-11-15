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
  precision: 0.9747
  recall: 0.9825
  f1: 0.9786
door:
  precision: 0.8679
  recall: 0.8874
  f1: 0.8776
  tp: 473
  pred: 545
  true: 533
window:
  precision: 0.9932
  recall: 0.9701
  f1: 0.9815
  tp: 292
  pred: 294
  true: 301
opening:
  precision: 0.8333
  recall: 1.0000
  f1: 0.9091
  tp: 5
  pred: 6
  true: 5
rooms:
  precision: 1.0000
  recall: 0.9957
  f1: 0.9978
  tp: 461
  pred: 461
  true: 463
edges:
  precision: 0.9926
  recall: 0.9926
  f1: 0.9926
  tp: 534
  pred: 538
  true: 538
room_type_accuracy: 1.0000
min(room F1, edge F1) by style:
  door_style=arc_leaf: 1.0000
  door_style=arc_only: 1.0000
  door_style=block: 0.9918
  door_style=bulge: 0.9727
  door_style=segments: 1.0000
  scheme=aia: 0.9905
  scheme=fr: 0.9864
  scheme=none: 1.0000
  scheme=numeric: 1.0000
  units=m: 0.9958
  units=mm: 0.9906
  wall_style=filled: 0.9756
  wall_style=hatched: 0.9970
  wall_style=lines: 1.0000
  wall_style=polylines: 1.0000
```

## Worst items / misses

- (0.0, 'rand_5043', "crash: GEOSException('TopologyException: side location conflict at 5.2359027629652726 7.1208036090837501. This can occur if the input geometry is invalid.')")
- (0.7, 'rand_5003', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 21.5, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (5, 5, 6), 'opening': (1, 1, 1), 'rooms': (7, 7, 8), 'edges': (7, 10, 10)})
- (0.9333333333333333, 'rand_5038', {'scheme': 'aia', 'wall_style': 'filled', 'door_style': 'block', 'angle': -1.6, 'units': 'm'}, {'door': (8, 8, 8), 'window': (2, 3, 5), 'opening': (1, 1, 1), 'rooms': (7, 7, 8), 'edges': (8, 8, 9)})
- (0.9523809523809523, 'rand_5049', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'block', 'angle': 0.0, 'units': 'm'}, {'door': (8, 11, 10), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (10, 11, 10)})
- (0.9702541247750354, 'rand_5054', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 90.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (5, 5, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.9775204176048443, 'rand_5035', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -13.0, 'units': 'mm'}, {'door': (3, 9, 9), 'window': (5, 6, 6), 'opening': (0, 1, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9779359186858756, 'rand_5004', {'scheme': 'numeric', 'wall_style': 'hatched', 'door_style': 'bulge', 'angle': 0.0, 'units': 'm'}, {'door': (1, 8, 7), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (7, 7, 7), 'edges': (7, 7, 7)})
- (0.9784390660813489, 'rand_5052', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 90.0, 'units': 'mm'}, {'door': (8, 9, 9), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9818902015612491, 'rand_5001', {'scheme': 'numeric', 'wall_style': 'filled', 'door_style': 'segments', 'angle': 0.0, 'units': 'm'}, {'door': (5, 5, 5), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (5, 5, 5), 'edges': (5, 5, 5)})
- (0.9859187984041304, 'rand_5015', {'scheme': 'numeric', 'wall_style': 'filled', 'door_style': 'arc_leaf', 'angle': 0.0, 'units': 'mm'}, {'door': (10, 10, 10), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (10, 10, 10), 'edges': (10, 10, 10)})
