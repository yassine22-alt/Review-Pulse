# Findings: ablate

240 drafts, 60 items, arms: rec_verify, expr, expr_verify, flat_cat_verify

## Headline (a draft counts as right only if it behaves like the reference on generated plans)

| Arm | Valid | Right | Valid but wrong | Rejected or failed | Median time |
|---|---|---|---|---|---|
| rec_verify | 16/60 = 27% (95% CI 17% to 39%) | 8/60 = 13% (95% CI 7% to 24%) | 8/60 = 13% (95% CI 7% to 24%) | 44/60 = 73% (95% CI 61% to 83%) | 20s |
| expr | 49/60 = 82% (95% CI 70% to 89%) | 40/60 = 67% (95% CI 54% to 77%) | 9/60 = 15% (95% CI 8% to 26%) | 11/60 = 18% (95% CI 11% to 30%) | 7s |
| expr_verify | 49/60 = 82% (95% CI 70% to 89%) | 43/60 = 72% (95% CI 59% to 81%) | 6/60 = 10% (95% CI 5% to 20%) | 11/60 = 18% (95% CI 11% to 30%) | 7s |
| flat_cat_verify | 11/60 = 18% (95% CI 11% to 30%) | 8/60 = 13% (95% CI 7% to 24%) | 3/60 = 5% (95% CI 2% to 14%) | 49/60 = 82% (95% CI 70% to 89%) | 29s |

A rule that is valid but wrong is the dangerous case: a reviewer could approve it.

## Why drafts fail (per arm, most common first)

**rec_verify** (44 failed)
- 30: rejected by the sentence check
- 7: invented collection
- 3: generation ran away (token cap or timeout)
- 2: form fields missing or wrong type
- 1: units or types do not fit
- 1: variable scope (unbound or shadowed)

**expr** (11 failed)
- 8: expression could not be parsed
- 2: invented fact name
- 1: units or types do not fit

**expr_verify** (11 failed)
- 9: expression could not be parsed
- 1: rejected by the sentence check
- 1: invented fact name

**flat_cat_verify** (49 failed)
- 25: dangling reference (node id that does not exist)
- 10: variable scope (unbound or shadowed)
- 5: generation ran away (token cap or timeout)
- 4: form fields missing or wrong type
- 3: rejected by the sentence check
- 2: units or types do not fit

## Why valid drafts are wrong (per arm)

**rec_verify** (8 valid but wrong)
- 8: not visible to any current check (structure or logic differs)

**expr** (9 valid but wrong)
- 4: not visible to any current check (structure or logic differs)
- 3: a category in the sentence is missing from the rule
- 1: a number in the sentence is not used by the rule
- 1: the rule uses a number the sentence does not state

**expr_verify** (6 valid but wrong)
- 6: not visible to any current check (structure or logic differs)

**flat_cat_verify** (3 valid but wrong)
- 3: not visible to any current check (structure or logic differs)

## Right, by rule shape

| rule shape | rec_verify | expr | expr_verify | flat_cat_verify |
|---|---|---|---|---|
| alternative | 2/6 | 6/6 | 6/6 | 1/6 |
| conditional | 0/6 | 2/6 | 3/6 | 0/6 |
| count | 0/6 | 4/6 | 4/6 | 0/6 |
| exemption | 0/6 | 5/6 | 5/6 | 0/6 |
| exists | 2/6 | 5/6 | 6/6 | 1/6 |
| range | 0/6 | 4/6 | 5/6 | 2/6 |
| ratio | 0/6 | 0/6 | 0/6 | 0/6 |
| scoped | 0/6 | 6/6 | 6/6 | 1/6 |
| threshold | 4/6 | 5/6 | 5/6 | 3/6 |
| total | 0/6 | 3/6 | 3/6 | 0/6 |

## Right, by language

| language | rec_verify | expr | expr_verify | flat_cat_verify |
|---|---|---|---|---|
| en | 2/34 | 25/34 | 25/34 | 3/34 |
| fr | 6/26 | 15/26 | 18/26 | 5/26 |

## Right, by concepts dev or held out

| concepts dev or held out | rec_verify | expr | expr_verify | flat_cat_verify |
|---|---|---|---|---|
| dev | 6/40 | 28/40 | 30/40 | 4/40 |
| test | 2/20 | 12/20 | 13/20 | 4/20 |

## Examples of valid but wrong drafts

- **expr** on "Chaque pièce doit avoir une largeur minimale d'au moins 2,2 m."
  - rule written: `forall rooms r where r.rooms_kind != 'corridor': r.rooms_min_width >= 2.2 m`
  - reference:    `forall rooms x: x.rooms_min_width >= 2.2 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_verify** on "Chaque pièce doit avoir une largeur minimale d'au moins 2,2 m."
  - rule written: `forall rooms r where r.rooms_kind != 'corridor': r.rooms_min_width >= 2.2 m`
  - reference:    `forall rooms x: x.rooms_min_width >= 2.2 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr** on "Where the number of occupants exceeds 50, the length of every ramp must be at least 800 cm."
  - rule written: `forall ramps r where r.occupants > 50: r.ramps_length >= 8 m`
  - reference:    `forall ramps x: x.ramps_length >= 8 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_verify** on "Where the number of occupants exceeds 50, the length of every ramp must be at least 800 cm."
  - rule written: `forall ramps r where r.occupants > 50: r.ramps_length >= 8 m`
  - reference:    `forall ramps x: x.ramps_length >= 8 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr** on "Dans les bâtiments de plus de 2 niveaux, chaque place accessible doit avoir une longueur d'au moins 480 cm."
  - rule written: `forall ramps r: r.ramps_length >= 4.8 m`
  - reference:    `forall bays x where x.bays_kind == 'accessible': x.bays_length >= 4.8 m`
  - cause: a category in the sentence is missing from the rule
- **rec_verify** on "Chaque couloir ayant une surface d'au moins 14 m² doit avoir une largeur minimale d'au moins 1,5 m."
  - rule written: `forall rooms x: x.rooms_kind == 'corridor' and x.rooms_area >= 14 m2 and x.rooms_min_width >= 1.5 m`
  - reference:    `forall rooms x where x.rooms_kind == 'corridor' and x.rooms_area >= 14 m2: x.rooms_min_width >= 1.5 m`
  - cause: not visible to any current check (structure or logic differs)
