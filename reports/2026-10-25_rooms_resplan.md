# Evaluation: rooms_resplan

- dataset: resplan (public data only: no real plans scored yet)
- items: 1632
- method: rules
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-24

## Metrics

```
plans: 1632
split: test
oracle_inputs: off
spaces_iou50:
  precision: 0.9955
  recall: 0.9934
  f1: 0.9944
  tp: 9718
  pred: 9762
  true: 9783
door_edges:
  precision: 0.9939
  recall: 0.9932
  f1: 0.9936
  tp: 10971
  pred: 11038
  true: 11046
exits:
  front_doors_true: 1629
  doors_labelled_exit: 3882
outdoor_spaces_not_scored: 2033
```

## Worst items / misses

- (0.769, 8271, {'rooms': (5, 7, 6), 'edges': (3, 5, 3)})
- (0.769, 2558, {'rooms': (5, 6, 7), 'edges': (5, 7, 7)})
- (0.8, 8577, {'rooms': (4, 5, 5), 'edges': (3, 6, 6)})
- (0.8, 13025, {'rooms': (2, 2, 3), 'edges': (2, 2, 3)})
- (0.833, 7274, {'rooms': (5, 6, 6), 'edges': (3, 7, 6)})
- (0.833, 16940, {'rooms': (5, 6, 6), 'edges': (2, 5, 7)})
- (0.857, 6385, {'rooms': (3, 4, 3), 'edges': (3, 4, 3)})
- (0.857, 9763, {'rooms': (3, 3, 4), 'edges': (3, 3, 4)})
- (0.857, 12049, {'rooms': (3, 4, 3), 'edges': (3, 4, 3)})
- (0.857, 5470, {'rooms': (3, 3, 4), 'edges': (3, 3, 4)})
