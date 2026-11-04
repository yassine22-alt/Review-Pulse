# Evaluation: raster

- dataset: cubicasa5k (public data only: no real plans scored yet)
- items: 100
- method: model_scan
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-25

## Metrics

```
plans: 100
split: test
model_scan:
  walls_3px:
    precision: 0.9304
    recall: 0.9742
    f1: 0.9518
  walls_iou: 0.7921
  door_iou50:
    precision: 0.8086
    recall: 0.8946
    f1: 0.8495
  door_iou30:
    precision: 0.8422
    recall: 0.9317
    f1: 0.8847
  window_iou50:
    precision: 0.8051
    recall: 0.8221
    f1: 0.8135
  window_iou30:
    precision: 0.8489
    recall: 0.8669
    f1: 0.8578
  rooms_iou50:
    precision: 0.9213
    recall: 0.8795
    f1: 0.8999
oracle:
  rooms_iou50:
    precision: 0.9645
    recall: 0.9845
    f1: 0.9744
```

## Worst items / misses

- none
