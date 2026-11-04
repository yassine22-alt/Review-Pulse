# Evaluation: random_pdf

- dataset: synth (public data only: no real plans scored yet)
- items: 60
- method: rules
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-27

## Metrics

```
n: 60
format: pdf
walls:
  precision: 0.9979
  recall: 0.9992
  f1: 0.9986
door:
  precision: 0.9982
  recall: 1.0000
  f1: 0.9991
  tp: 546
  pred: 547
  true: 546
window:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 308
  pred: 308
  true: 308
opening:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 5
  pred: 5
  true: 5
rooms:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 474
  pred: 474
  true: 474
edges:
  precision: 1.0000
  recall: 1.0000
  f1: 1.0000
  tp: 551
  pred: 551
  true: 551
room_type_accuracy: 1.0000
min(room F1, edge F1) by style:
  door_style=arc_leaf: 1.0000
  door_style=arc_only: 1.0000
  door_style=block: 1.0000
  door_style=bulge: 1.0000
  door_style=segments: 1.0000
  scheme=aia: 1.0000
  scheme=fr: 1.0000
  scheme=none: 1.0000
  scheme=numeric: 1.0000
  units=m: 1.0000
  units=mm: 1.0000
  wall_style=filled: 1.0000
  wall_style=hatched: 1.0000
  wall_style=lines: 1.0000
  wall_style=polylines: 1.0000
```

## Worst items / misses

- (0.9714529898866712, 'rand_5020', {'scheme': 'none', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 0.0, 'units': 'm'}, {'door': (9, 9, 9), 'window': (5, 5, 5), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9842938609367625, 'rand_5023', {'scheme': 'none', 'wall_style': 'hatched', 'door_style': 'segments', 'angle': 90.0, 'units': 'mm'}, {'door': (10, 10, 10), 'window': (6, 6, 6), 'opening': (1, 1, 1), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.991051590647758, 'rand_5034', {'scheme': 'none', 'wall_style': 'lines', 'door_style': 'block', 'angle': 0.0, 'units': 'mm'}, {'door': (12, 12, 12), 'window': (5, 5, 5), 'opening': (0, 0, 0), 'rooms': (11, 11, 11), 'edges': (12, 12, 12)})
- (0.9921920711320433, 'rand_5057', {'scheme': 'none', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -3.7, 'units': 'mm'}, {'door': (12, 12, 12), 'window': (5, 5, 5), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (12, 12, 12)})
- (0.995986969982605, 'rand_5054', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'bulge', 'angle': 90.0, 'units': 'm'}, {'door': (11, 11, 11), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (9, 9, 9), 'edges': (11, 11, 11)})
- (0.9965085319165098, 'rand_5052', {'scheme': 'none', 'wall_style': 'filled', 'door_style': 'arc_only', 'angle': 90.0, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (4, 4, 4), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
- (0.9968796897302066, 'rand_5032', {'scheme': 'fr', 'wall_style': 'filled', 'door_style': 'segments', 'angle': 0.0, 'units': 'mm'}, {'door': (15, 15, 15), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (14, 14, 14), 'edges': (15, 15, 15)})
- (0.9969554743681875, 'rand_5014', {'scheme': 'fr', 'wall_style': 'polylines', 'door_style': 'block', 'angle': 0.0, 'units': 'mm'}, {'door': (10, 10, 10), 'window': (8, 8, 8), 'opening': (0, 0, 0), 'rooms': (11, 11, 11), 'edges': (10, 10, 10)})
- (0.9976760352486936, 'rand_5017', {'scheme': 'numeric', 'wall_style': 'polylines', 'door_style': 'arc_leaf', 'angle': 0.0, 'units': 'mm'}, {'door': (11, 11, 11), 'window': (7, 7, 7), 'opening': (0, 0, 0), 'rooms': (10, 10, 10), 'edges': (11, 11, 11)})
- (0.9982971339746683, 'rand_5035', {'scheme': 'aia', 'wall_style': 'hatched', 'door_style': 'arc_leaf', 'angle': -13.0, 'units': 'mm'}, {'door': (9, 9, 9), 'window': (6, 6, 6), 'opening': (0, 0, 0), 'rooms': (8, 8, 8), 'edges': (9, 9, 9)})
