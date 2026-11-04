# Evaluation: random_pdf

- dataset: synth (public data only: no real plans scored yet)
- items: 60
- method: learned
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-28

## Metrics

```
n: 60
format: pdf
walls:
  precision: 0.9912
  recall: 0.9991
  f1: 0.9952
door:
  precision: 0.9783
  recall: 0.9927
  f1: 0.9855
  tp: 542
  pred: 554
  true: 546
window:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 308
  pred: 308
  true: 308
opening:
  precision: 0.5556
  recall: 1.0000
  f1: 0.7143
  tp: 5
  pred: 9
  true: 5
rooms:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 474
  pred: 474
  true: 474
edges:
  precision: 0.9928
  recall: 0.9982
  f1: 0.9955
  tp: 550
  pred: 554
  true: 551
room_type_accuracy: 1.0000
min(room F1, edge F1) by style:
  door_style=arc_leaf: 1.0000
  door_style=arc_only: 0.9625
  door_style=block: 1.0000
  door_style=bulge: 1.0000
  door_style=segments: 1.0000
  scheme=aia: 1.0000
  scheme=fr: 0.9970
  scheme=none: 0.9934
  scheme=numeric: 0.9921
  units=m: 1.0000
  units=mm: 0.9918
  wall_style=filled: 0.9925
  wall_style=hatched: 1.0000
  wall_style=lines: 1.0000
  wall_style=polylines: 0.9890
```

## Worst items / misses

- (0.8571428571428572, 'rand_5058', {'scheme': 'numeric', 'wall_style': 'polylines', 'door_style': 'arc_only', 'angle': -11.4, 'units': 'mm'}, {'door': (8, 10, 10), 'window': (3, 3, 3), 'opening': (0, 2, 0), 'rooms': (7, 7, 7), 'edges': (9, 11, 10)})
- (0.9333333333333333, 'rand_5037', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 25.9, 'units': 'mm'}, {'door': (6, 7, 7), 'window': (5, 5, 5), 'opening': (0, 1, 0), 'rooms': (6, 6, 6), 'edges': (7, 8, 7)})
- (0.9473684210526316, 'rand_5052', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 90.0, 'units': 'mm'}, {'door': (8, 9, 9), 'window': (4, 4, 4), 'opening': (0, 1, 0), 'rooms': (8, 8, 8), 'edges': (9, 10, 9)})
- (0.9686296641897936, 'rand_5038', {'scheme': 'aia', 'wall_style': 'filled', 'door_style': 'block', 'angle': -1.6, 'units': 'm'}, {'door': (8, 8, 8), 'window': (5, 5, 5), 'opening': (1, 1, 1), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9730935427518973, 'rand_5059', {'scheme': 'numeric', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 90.0, 'units': 'mm'}, {'door': (8, 8, 8), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (7, 7, 7), 'edges': (8, 8, 8)})
- (0.9837526903553291, 'rand_5035', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -13.0, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9843017567999198, 'rand_5001', {'scheme': 'numeric', 'wall_style': 'filled', 'door_style': 'segments', 'angle': 0.0, 'units': 'm'}, {'door': (5, 5, 5), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (5, 5, 5), 'edges': (5, 5, 5)})
- (0.9846280228865403, 'rand_5043', {'scheme': 'numeric', 'wall_style': 'filled', 'door_style': 'segments', 'angle': -37.4, 'units': 'm'}, {'door': (13, 13, 13), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (11, 11, 11), 'edges': (13, 13, 13)})
- (0.9868818438986252, 'rand_5054', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 90.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.9878299730298475, 'rand_5003', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 21.5, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (6, 6, 6), 'opening': (1, 1, 1), 'rooms': (8, 8, 8), 'edges': (10, 10, 10)})
