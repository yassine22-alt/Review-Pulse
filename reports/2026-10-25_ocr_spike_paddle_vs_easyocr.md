# Evaluation: ocr_spike

- dataset: fptxt_cubicasa_test (public data only: no real plans scored yet)
- items: 30
- method: paddle_vs_easyocr
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-25

## Metrics

```
recognition_25_hand_transcribed_crops:
  easyocr:
    cer_mean: 0.6120
    exact: 9
    n: 25
    seconds: 37.6000
  paddle:
    cer_mean: 0.1204
    exact: 18
    n: 25
    seconds: 194.3000
recognition_paddle_rotations:
  0:
    cer_mean: 0.1604
    exact: 17
  0,90:
    cer_mean: 0.1404
    exact: 18
  0,90,270,180:
    cer_mean: 0.1204
    exact: 18
detection_fptxt_iou30_30_test_pages:
  easyocr:
    precision: 0.8817
    recall: 0.2046
    f1: 0.3321
    pages: 30
    truth_boxes: 1129
    sec_per_page: 3.5000
  paddle:
    precision: 0.8300
    recall: 0.7830
    f1: 0.8058
    pages: 30
    truth_boxes: 1129
    sec_per_page: 116.5000
```

## Worst items / misses

- paddle: a_06.png truth 'PK' read 'TPK'
- paddle: a_11.png truth 'SK' read '5K'
- paddle: a_12.png truth '1797,5' read '1797.5'
- paddle: a_15.png truth 'OH' read 'HO'
- paddle: a_16.png truth '3h' read '34'
- paddle: b_02.png truth '3,1m²' read '3.1m²'
- paddle: b_08.png truth '120x370' read '120m370'
- CVC-FP (FP-TXT's second set) is not downloadable any more: detection measured on the CubiCasa part only
- crops transcribed visually by Claude; 11 of 36 sampled crops excluded as illegible/ambiguous (reports/ocr_spike/gt_notes.json)
- timings on a laptop CPU while the segmentation model trained on the same machine
