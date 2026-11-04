# Evaluation: drafting

- dataset: i4_gold (public data only: no real plans scored yet)
- items: 30
- method: ollama-qwen2.5_7b
- oracle inputs: off
- commit: 9b9a639
- date: 2026-10-24

## Metrics

```
all:
  clauses: 30
  label_accuracy: 0.9333
  non_checkable_refused: 4/5
  fn_recall: 0.7600
  fn_precision: 0.7917
  op_recall: 0.9333
  op_precision: 0.9333
  value_recall: 0.9333
  value_precision: 0.9333
  unit_recall: 1.0000
  unit_precision: 0.7333
  scope_recall: 0.9231
  scope_precision: 0.6000
  exact_rules: 19
dev (odd ids):
  clauses: 15
  label_accuracy: 0.9333
  non_checkable_refused: 2/2
  fn_recall: 0.7692
  fn_precision: 0.8333
  op_recall: 1.0000
  op_precision: 0.8889
  value_recall: 1.0000
  value_precision: 0.8889
  unit_recall: 1.0000
  unit_precision: 0.6667
  scope_recall: 0.8571
  scope_precision: 0.6000
  exact_rules: 10
test (even ids, held out):
  clauses: 15
  label_accuracy: 0.9333
  non_checkable_refused: 2/3
  fn_recall: 0.7500
  fn_precision: 0.7500
  op_recall: 0.8571
  op_precision: 1.0000
  value_recall: 0.8571
  value_precision: 1.0000
  unit_recall: 1.0000
  unit_precision: 0.8333
  scope_recall: 1.0000
  scope_precision: 0.6000
  exact_rules: 9
seconds_per_clause: 7.8600
```

## Worst items / misses

- ('G01', 'dev', 'from_drawings', 'exact')
- ('G02', 'test', 'from_drawings', 'exact')
- ('G03', 'dev', 'from_drawings', 'exact')
- ('G04', 'test', 'from_drawings', 'exact')
- ('G05', 'dev', 'from_drawings', 'exact')
- ('G06', 'test', 'from_drawings', 'exact')
- ('G07', 'dev', 'from_drawings', 'exact')
- ('G08', 'test', 'from_drawings', 'exact')
- ('G09', 'dev', 'from_drawings', 'exact')
- ('G10', 'test', 'from_drawings', 'exact')
- ('G11', 'dev', 'from_drawings', "fn: want exists_path got forbidden_link; scope: want ('rooms', frozenset({'bedroom'})) got ('pairs', frozenset({frozenset({'bedroom'})})); avoid: want ['bedroom'] got []")
- ('G12', 'test', 'from_drawings', 'exact')
- ('G13', 'dev', 'from_drawings', 'exact')
- ('G14', 'test', 'from_drawings', 'fn: want count_exits got exists_path; op: want >= got None; value: want 1 got None')
- ('G15', 'dev', 'from_drawings', 'exact')
- ('G16', 'test', 'from_drawings', 'exact')
- ('G17', 'dev', 'from_drawings', 'exact')
- ('G18', 'test', 'from_drawings', 'fn: want ratio got area_m2')
- ('G19', 'dev', 'from_drawings', 'exact')
- ('G20', 'test', 'from_drawings', 'exact')
- ('G21', 'dev', 'from_drawings', 'exact')
- ('G22', 'test', 'from_drawings', 'fn: want drawn_vs_stated got sum_parts')
- ('G23', 'dev', 'not_checkable', 'fn: want join got None')
- ('G24', 'test', 'from_drawings', 'exact')
- ('G25', 'dev', 'from_drawings', 'fn: want stated_vs_computed_area got area_m2')
- ('G26', 'test', 'from_drawings', 'SHOULD REFUSE')
- ('G27', 'dev', 'not_checkable', 'refused correctly')
- ('G28', 'test', 'not_checkable', 'refused correctly')
- ('G29', 'dev', 'not_checkable', 'refused correctly')
- ('G30', 'test', 'needs_other_data', 'refused correctly')
