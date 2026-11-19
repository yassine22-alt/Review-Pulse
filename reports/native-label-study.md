# Native-label drawing study

References frozen at `c1c452b3` before inference. Assistant annotations, no independent review. All drawings stayed local.

| Drawing / reviewed scope | Named space points | Bedrooms classified | Door / window candidates | Selected opening boxes hit | Schedules |
| --- | --- | --- | --- | --- | --- |
| chief-a7 | 0/17 | 0/4 | 0 / 0 | 0/6 | 0/2 |
| uk-proposed | 4/14 | 2/3 | 2 / 33 | 1/4 | 0/0 |
| uk-existing-single | 0/7 | 0/1 | 0 / 0 | 0/4 | 0/0 |
| uk-existing-pair | 4/5 | 2/2 | 8 / 1 | 2/4 | 0/0 |

The three UK PDFs came from a planning-document CDN, not verified council archives; source URLs, hashes and scope boxes are in the frozen labels. These are three distinct architects/layout styles, but not a representative or independently sampled benchmark.

The implementation already used native room labels before this change. The new experimental naming pass rejects ambiguous containment and records provenance; it does not create room geometry, confirm classification or mark inventories complete. The trained classifier supplies primitive geometry, not room-use predictions; no trained room-type fallback exists. Unknown labels remain unknown.

Selected label points may be functional parts of an open-plan room. Point containment and name matching are not polygon-IoU room recall. Four opening boxes per new drawing (two doors, two windows) are partial annotations: raw candidate counts and box hits cannot establish global precision/recall. A-7 retains its original six-opening subset. No schedules are present in the three selected UK review scopes; 0/0 is not schedule accuracy. A-7 recovers 0/2 schedules.

Some original room boundaries are label-seeded inferences; the naming pass flags them and never treats them as confirmed enclosure. Review scopes were explicitly supplied; view selection was not automated. No tuning on the sealed fourth regulation took place.

[Full results and traces](native-label-study-results.json).
