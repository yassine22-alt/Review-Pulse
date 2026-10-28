# Evaluation: random_pdf

- dataset: synth (public data only: no real plans scored yet)
- items: 60
- method: learned
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-27

## Metrics

```
n: 60
format: pdf
walls:
  precision: 0.9876
  recall: 0.9989
  f1: 0.9932
door:
  precision: 0.8723
  recall: 0.8883
  f1: 0.8802
  tp: 485
  pred: 556
  true: 546
window:
  precision: 0.9868
  recall: 0.9675
  f1: 0.9770
  tp: 298
  pred: 302
  true: 308
opening:
  precision: 0.6250
  recall: 1.0000
  f1: 0.7692
  tp: 5
  pred: 8
  true: 5
rooms:
  precision: 1.0000
  recall: 0.9958
  f1: 0.9979
  tp: 472
  pred: 472
  true: 474
edges:
  precision: 0.9927
  recall: 0.9909
  f1: 0.9918
  tp: 546
  pred: 550
  true: 551
room_type_accuracy: 1.0000
min(room F1, edge F1) by style:
  door_style=arc_leaf: 1.0000
  door_style=arc_only: 0.9857
  door_style=block: 0.9952
  door_style=bulge: 1.0000
  door_style=segments: 0.9856
  scheme=aia: 0.9944
  scheme=fr: 1.0000
  scheme=none: 1.0000
  scheme=numeric: 0.9816
  units=m: 0.9894
  units=mm: 0.9969
  wall_style=filled: 0.9814
  wall_style=hatched: 1.0000
  wall_style=lines: 1.0000
  wall_style=polylines: 0.9923
```

## Worst items / misses

- (0.7692307692307693, 'rand_5043', {'scheme': 'numeric', 'wall_style': 'filled', 'door_style': 'segments', 'angle': -37.4, 'units': 'm'}, {'door': (13, 13, 13), 'window': (3, 4, 7), 'opening': (0, 0, 0), 'rooms': (10, 10, 11), 'edges': (10, 13, 13)})
- (0.9, 'rand_5058', {'scheme': 'numeric', 'wall_style': 'polylines', 'door_style': 'arc_only', 'angle': -11.4, 'units': 'mm'}, {'door': (8, 10, 10), 'window': (2, 3, 3), 'opening': (0, 1, 0), 'rooms': (7, 7, 7), 'edges': (9, 10, 10)})
- (0.9333333333333333, 'rand_5038', {'scheme': 'aia', 'wall_style': 'filled', 'door_style': 'block', 'angle': -1.6, 'units': 'm'}, {'door': (8, 8, 8), 'window': (4, 4, 5), 'opening': (1, 1, 1), 'rooms': (7, 7, 8), 'edges': (8, 8, 9)})
- (0.9730403994955579, 'rand_5054', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 90.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.9744874084362507, 'rand_5052', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 90.0, 'units': 'mm'}, {'door': (8, 9, 9), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.974733133985689, 'rand_5035', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -13.0, 'units': 'mm'}, {'door': (1, 9, 9), 'window': (5, 6, 6), 'opening': (0, 2, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9785113194362138, 'rand_5004', {'scheme': 'numeric', 'wall_style': 'hatched', 'door_style': 'bulge', 'angle': 0.0, 'units': 'm'}, {'door': (5, 8, 7), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (7, 7, 7), 'edges': (7, 7, 7)})
- (0.9799905119730623, 'rand_5029', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'block', 'angle': 0.0, 'units': 'mm'}, {'door': (10, 10, 10), 'window': (4, 5, 5), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (10, 10, 10)})
- (0.9808112482661582, 'rand_5024', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'block', 'angle': 0.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (3, 3, 4), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (11, 11, 11)})
- (0.9811026421559755, 'rand_5044', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 0.0, 'units': 'm'}, {'door': (10, 10, 10), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (10, 10, 10)})
