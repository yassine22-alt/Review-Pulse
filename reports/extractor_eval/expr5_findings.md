# Findings: expr5

60 drafts, 60 items, arms: expr_verify

## Headline (a draft counts as right only if it behaves like the reference on generated plans)

| Arm | Valid | Right | Valid but wrong | (of which differ only on UNRESOLVED vs a verdict) | Rejected or failed | Median time |
|---|---|---|---|---|---|---|
| expr_verify | 53/60 = 88% (95% CI 78% to 94%) | 50/60 = 83% (95% CI 72% to 91%) | 3/60 = 5% (95% CI 2% to 14%) | 2 | 7/60 = 12% (95% CI 6% to 22%) | 8s |

A rule that is valid but wrong is the dangerous case: a reviewer could approve it.

## Why drafts fail (per arm, most common first)

**expr_verify** (7 failed)
- 4: units or types do not fit
- 2: invented fact name
- 1: expression could not be parsed

## Why valid drafts are wrong (per arm)

**expr_verify** (3 valid but wrong)
- 3: not visible to any current check (structure or logic differs)

## Right, by rule shape

| rule shape | expr_verify |
|---|---|
| alternative | 6/6 |
| conditional | 6/6 |
| count | 6/6 |
| exemption | 6/6 |
| exists | 5/6 |
| range | 4/6 |
| ratio | 0/6 |
| scoped | 6/6 |
| threshold | 6/6 |
| total | 5/6 |

## Right, by language

| language | expr_verify |
|---|---|
| en | 30/34 |
| fr | 20/26 |

## Right, by concepts dev or held out

| concepts dev or held out | expr_verify |
|---|---|
| dev | 35/40 |
| test | 15/20 |

## Examples of valid but wrong drafts

- **expr_verify** on "The sum of the clear heights of external doors shall be at least 40 % of the sum of the clear heights of all doors."
  - rule written: `sum(doors d where d.doors_kind == 'external': d.doors_height) >= 0.4 * sum(doors d: d.doors_height)`
  - reference:    `sum(doors x where x.doors_kind == 'external': x.doors_height) / sum(doors x: x.doors_height) >= 0.4`
  - cause: not visible to any current check (structure or logic differs)
- **expr_verify** on "Chaque gaine doit avoir une longueur comprise entre 5 m et 10 m."
  - rule written: `forall exits e: e.exits_width >= 5 m and e.exits_width <= 10 m`
  - reference:    `forall ducts x: x.ducts_length >= 5 m and x.ducts_length <= 10 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_verify** on "The sum of the diameters of supply ducts shall be at least 25 % of the sum of the diameters of all ducts."
  - rule written: `sum(ducts d where d.ducts_kind == 'supply': d.ducts_diameter) >= 0.25 * sum(ducts d: d.ducts_diameter)`
  - reference:    `sum(ducts x where x.ducts_kind == 'supply': x.ducts_diameter) / sum(ducts x: x.ducts_diameter) >= 0.25`
  - cause: not visible to any current check (structure or logic differs)
