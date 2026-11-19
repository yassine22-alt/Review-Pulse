# Polygonized wall-line study

References frozen at `5c194583` before running. Four real vector-PDF source scopes reuse the unchanged author labels; the only DXF is explicitly synthetic. No independent reviewer.

| Scope | Reference points inside faces | Bedrooms named | Opening box hits | Face/cut/dangle counts |
| --- | --- | --- | --- | --- |
| chief-a7 | 0/17 | 0/4 | 0/6 | 0/0/18 |
| uk-proposed | 0/14 | 0/3 | 1/4 | 1/0/107 |
| uk-existing-single | 0/7 | 0/1 | 0/4 | 1/0/7 |
| uk-existing-pair | 1/5 | 0/2 | 2/4 | 8/5/76 |
| cad-control (synthetic) | 3/3 | 2/2 | 0/0 | 3/0/0 |

Exact polygonization does not perform well on these real classified wall networks. Missing walls and gaps remain open; the algorithm does not infer closures. It is worse on these PDF scopes than the previous barrier-based builder, and is not promoted to the application default. Native text cannot name an enclosure that the wall network does not establish.

The synthetic DXF establishes three closed enclosures, two labeled bedrooms and one intentionally unlabeled region. It has no openings, so 0/0 is not opening accuracy. This validates a closed-line control, not real CAD performance. No Moroccan drawing or real DXF was found locally, and none was invented for the benchmark.

These are reference-point containment and naming checks, not polygon-IoU room recall. Opening boxes are partial; candidate counts cannot establish global precision/recall. Centerline faces are not net floor areas; no result here is used as a confirmed area or complete inventory. Full diagnostics and raw candidate counts: [results](polygonize-results.json).
