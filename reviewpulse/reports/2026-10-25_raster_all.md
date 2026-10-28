# Evaluation: raster

- dataset: cubicasa5k (public data only: no real plans scored yet)
- items: 100
- method: all
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-25

## Metrics

```
plans: 100
split: test
rules:
  walls_3px:
    precision: 0.5727
    recall: 0.8799
    f1: 0.6938
  walls_iou: 0.4058
  door_iou50:
    precision: 0.0000
    recall: 0.0000
    f1: 0.0000
  door_iou30:
    precision: 0.0000
    recall: 0.0000
    f1: 0.0000
  window_iou50:
    precision: 0.0000
    recall: 0.0000
    f1: 0.0000
  window_iou30:
    precision: 0.0000
    recall: 0.0000
    f1: 0.0000
  rooms_iou50:
    precision: 0.4539
    recall: 0.2681
    f1: 0.3371
model:
  walls_3px:
    precision: 0.9302
    recall: 0.9788
    f1: 0.9539
  walls_iou: 0.7978
  door_iou50:
    precision: 0.7963
    recall: 0.8810
    f1: 0.8365
  door_iou30:
    precision: 0.8325
    recall: 0.9210
    f1: 0.8745
  window_iou50:
    precision: 0.7916
    recall: 0.8009
    f1: 0.7963
  window_iou30:
    precision: 0.8452
    recall: 0.8551
    f1: 0.8501
  rooms_iou50:
    precision: 0.9113
    recall: 0.8381
    f1: 0.8731
fusion:
  walls_3px:
    precision: 0.7352
    recall: 0.9829
    f1: 0.8412
  walls_iou: 0.6387
  door_iou50:
    precision: 0.7963
    recall: 0.8810
    f1: 0.8365
  door_iou30:
    precision: 0.8325
    recall: 0.9210
    f1: 0.8745
  window_iou50:
    precision: 0.7916
    recall: 0.8009
    f1: 0.7963
  window_iou30:
    precision: 0.8452
    recall: 0.8551
    f1: 0.8501
  rooms_iou50:
    precision: 0.8395
    recall: 0.7992
    f1: 0.8188
oracle:
  rooms_iou50:
    precision: 0.9645
    recall: 0.9845
    f1: 0.9744
```

## Worst items / misses

- ((1, 1, 4), 'high_quality_8380')
- ((4, 5, 14), 'high_quality_architectural_5135')
- ((6, 21, 19), 'high_quality_architectural_3527')
- ((1, 4, 3), 'high_quality_architectural_3781')
- ((2, 2, 6), 'high_quality_3247')
- ((3, 4, 8), 'high_quality_1282')
- ((2, 3, 5), 'high_quality_architectural_3517')
- ((2, 3, 5), 'high_quality_6624')
- ((1, 3, 2), 'high_quality_architectural_239')
- ((1, 1, 2), 'high_quality_architectural_1838')
