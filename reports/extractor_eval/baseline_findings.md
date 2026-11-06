# Findings: baseline

150 drafts, 30 items, arms: baseline, rec_ex, flat, flat_cat, flat_cat_repair

## Headline (a draft counts as right only if it behaves like the reference on generated plans)

| Arm | Valid | Right | Valid but wrong | Rejected or failed | Median time |
|---|---|---|---|---|---|
| baseline | 1/30 = 3% (95% CI 1% to 17%) | 0/30 = 0% (95% CI 0% to 11%) | 1/30 = 3% (95% CI 1% to 17%) | 29/30 = 97% (95% CI 83% to 99%) | 65s |
| rec_ex | 24/30 = 80% (95% CI 63% to 90%) | 3/30 = 10% (95% CI 3% to 26%) | 21/30 = 70% (95% CI 52% to 83%) | 6/30 = 20% (95% CI 10% to 37%) | 12s |
| flat | 7/30 = 23% (95% CI 12% to 41%) | 4/30 = 13% (95% CI 5% to 30%) | 3/30 = 10% (95% CI 3% to 26%) | 23/30 = 77% (95% CI 59% to 88%) | 17s |
| flat_cat | 8/30 = 27% (95% CI 14% to 44%) | 4/30 = 13% (95% CI 5% to 30%) | 4/30 = 13% (95% CI 5% to 30%) | 22/30 = 73% (95% CI 56% to 86%) | 18s |
| flat_cat_repair | 11/30 = 37% (95% CI 22% to 54%) | 4/30 = 13% (95% CI 5% to 30%) | 7/30 = 23% (95% CI 12% to 41%) | 19/30 = 63% (95% CI 46% to 78%) | 36s |

A rule that is valid but wrong is the dangerous case: a reviewer could approve it.

## Why drafts fail (per arm, most common first)

**baseline** (29 failed)
- 16: generation ran away (token cap or timeout)
- 6: form fields missing or wrong type
- 3: quote not found in the clause
- 2: invented fact name
- 2: units or types do not fit

**rec_ex** (6 failed)
- 2: invented collection
- 2: units or types do not fit
- 1: variable scope (unbound or shadowed)
- 1: form fields missing or wrong type

**flat** (23 failed)
- 10: dangling reference (node id that does not exist)
- 4: variable scope (unbound or shadowed)
- 4: generation ran away (token cap or timeout)
- 2: invented collection
- 1: invented fact name
- 1: cycle between nodes
- 1: form fields missing or wrong type

**flat_cat** (22 failed)
- 10: dangling reference (node id that does not exist)
- 6: variable scope (unbound or shadowed)
- 5: generation ran away (token cap or timeout)
- 1: units or types do not fit

**flat_cat_repair** (19 failed)
- 10: dangling reference (node id that does not exist)
- 5: variable scope (unbound or shadowed)
- 3: generation ran away (token cap or timeout)
- 1: other

## Why valid drafts are wrong (per arm)

**baseline** (1 valid but wrong)
- 1: a comparison points the wrong way

**rec_ex** (21 valid but wrong)
- 11: a category in the sentence is missing from the rule
- 8: a number in the sentence is not used by the rule
- 2: not visible to any current check (structure or logic differs)

**flat** (3 valid but wrong)
- 2: a category in the sentence is missing from the rule
- 1: not visible to any current check (structure or logic differs)

**flat_cat** (4 valid but wrong)
- 3: a category in the sentence is missing from the rule
- 1: not visible to any current check (structure or logic differs)

**flat_cat_repair** (7 valid but wrong)
- 4: a category in the sentence is missing from the rule
- 1: a comparison points the wrong way
- 1: not visible to any current check (structure or logic differs)
- 1: a number in the sentence is not used by the rule

## Right, by rule shape

| rule shape | baseline | rec_ex | flat | flat_cat | flat_cat_repair |
|---|---|---|---|---|---|
| alternative | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 |
| conditional | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| count | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| exemption | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| exists | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| range | 0/3 | 0/3 | 1/3 | 1/3 | 1/3 |
| ratio | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| scoped | 0/3 | 0/3 | 1/3 | 1/3 | 1/3 |
| threshold | 0/3 | 2/3 | 2/3 | 2/3 | 2/3 |
| total | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

## Right, by language

| language | baseline | rec_ex | flat | flat_cat | flat_cat_repair |
|---|---|---|---|---|---|
| en | 0/16 | 0/16 | 1/16 | 1/16 | 1/16 |
| fr | 0/14 | 3/14 | 3/14 | 3/14 | 3/14 |

## Right, by concepts dev or held out

| concepts dev or held out | baseline | rec_ex | flat | flat_cat | flat_cat_repair |
|---|---|---|---|---|---|
| dev | 0/20 | 1/20 | 1/20 | 1/20 | 1/20 |
| test | 0/10 | 2/10 | 3/10 | 3/10 | 3/10 |

## Examples of valid but wrong drafts

- **rec_ex** on "Chaque pièce doit avoir une surface d'au plus 16 m²."
  - rule written: `forall rooms x: x.rooms_area <= 16 m2`
  - reference:    `forall rooms x: x.rooms_area <= 16 m2`
  - cause: not visible to any current check (structure or logic differs)
- **flat** on "Chaque pièce doit avoir une surface d'au plus 16 m²."
  - rule written: `(forall rooms x: x.rooms_area <= 16 m2) == (forall rooms x: x.rooms_area <= 16 m2)`
  - reference:    `forall rooms x: x.rooms_area <= 16 m2`
  - cause: not visible to any current check (structure or logic differs)
- **rec_ex** on "Dans les bâtiments de plus de 5 niveaux, chaque porte coupe-feu doit avoir une largeur de passage d'au moins 0,7 m."
  - rule written: `forall doors x: x.doors_width >= 0.7 m`
  - reference:    `forall doors x where x.doors_kind == 'fire': x.doors_width >= 0.7 m`
  - cause: a category in the sentence is missing from the rule
- **rec_ex** on "Chaque porte intérieure doit avoir une largeur de passage d'au moins 0,75 m, sauf dans les bâtiments d'au plus 8 m de hauteur."
  - rule written: `forall doors x: x.doors_width >= 0.75 m`
  - reference:    `forall doors x where x.doors_kind == 'internal': x.doors_width >= 0.75 m`
  - cause: a category in the sentence is missing from the rule
- **rec_ex** on "Chaque place de stationnement doit avoir une largeur d'au moins 2500 mm, sauf dans les bâtiments de 2 niveaux ou moins."
  - rule written: `forall bays x: x.bays_width >= 2.5 m`
  - reference:    `forall bays x: x.bays_width >= 2.5 m`
  - cause: a number in the sentence is not used by the rule
- **flat_cat_repair** on "Chaque place de stationnement doit avoir une largeur d'au moins 2500 mm, sauf dans les bâtiments de 2 niveaux ou moins."
  - rule written: `bays.bays_width >= 2.5 m and not building.storeys < 2`
  - reference:    `forall bays x: x.bays_width >= 2.5 m`
  - cause: a comparison points the wrong way
