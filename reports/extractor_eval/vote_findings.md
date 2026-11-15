# Findings: vote

60 drafts, 60 items, arms: expr_vote

## Headline (a draft counts as right only if it behaves like the reference on generated plans)

| Arm | Valid | Right | Valid but wrong | Rejected or failed | Median time |
|---|---|---|---|---|---|
| expr_vote | 52/60 = 87% (95% CI 76% to 93%) | 44/60 = 73% (95% CI 61% to 83%) | 8/60 = 13% (95% CI 7% to 24%) | 8/60 = 13% (95% CI 7% to 24%) | 27s |

A rule that is valid but wrong is the dangerous case: a reviewer could approve it.

## Why drafts fail (per arm, most common first)

**expr_vote** (8 failed)
- 8: other

## Why valid drafts are wrong (per arm)

**expr_vote** (8 valid but wrong)
- 8: not visible to any current check (structure or logic differs)

## Right, by rule shape

| rule shape | expr_vote |
|---|---|
| alternative | 6/6 |
| conditional | 3/6 |
| count | 5/6 |
| exemption | 5/6 |
| exists | 6/6 |
| range | 5/6 |
| ratio | 0/6 |
| scoped | 6/6 |
| threshold | 5/6 |
| total | 3/6 |

## Right, by language

| language | expr_vote |
|---|---|
| en | 26/34 |
| fr | 18/26 |

## Right, by concepts dev or held out

| concepts dev or held out | expr_vote |
|---|---|
| dev | 29/40 |
| test | 15/20 |

## Examples of valid but wrong drafts

- **expr_vote** on "Chaque pièce doit avoir une largeur minimale d'au moins 2,2 m."
  - rule written: `forall rooms r where r.rooms_kind != 'corridor': r.rooms_min_width >= 2.2 m`
  - reference:    `forall rooms x: x.rooms_min_width >= 2.2 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_vote** on "Where the number of occupants exceeds 50, the length of every ramp must be at least 800 cm."
  - rule written: `forall ramps r where r.occupants > 50: r.ramps_length >= 8 m`
  - reference:    `forall ramps x: x.ramps_length >= 8 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_vote** on "Chaque place de stationnement doit avoir une largeur d'au moins 2500 mm, sauf dans les bâtiments de 2 niveaux ou moins."
  - rule written: `forall bays bay where bay.bays_kind == 'standard': bay.bays_width >= 2.5 m`
  - reference:    `forall bays x: x.bays_width >= 2.5 m`
  - cause: not visible to any current check (structure or logic differs)
- **expr_vote** on "The sum of the clear heights of external doors shall be at least 40 % of the sum of the clear heights of all doors."
  - rule written: `sum(doors d where d.doors_kind == 'external': d.doors_height) >= 0.4 * sum(doors d: d.doors_height)`
  - reference:    `sum(doors x where x.doors_kind == 'external': x.doors_height) / sum(doors x: x.doors_height) >= 0.4`
  - cause: not visible to any current check (structure or logic differs)
- **expr_vote** on "The sum of the clear widths of external doors shall be at least 10% of the sum of the clear widths of all doors."
  - rule written: `sum(exits e where e.exits_kind == 'external': e.exits_width) >= 0.1 * sum(doors d: d.doors_width)`
  - reference:    `sum(doors x where x.doors_kind == 'external': x.doors_width) / sum(doors x: x.doors_width) >= 0.1`
  - cause: not visible to any current check (structure or logic differs)
- **expr_vote** on "Dans les bâtiments de plus de 100 m² de surface, chaque poutre en acier doit avoir une hauteur d'au moins 0,4 m."
  - rule written: `forall beams b where b.beams_kind == 'steel' and building.gross_area > 100 m2: b.beams_depth >= 0.4 m`
  - reference:    `forall beams x where x.beams_kind == 'steel': x.beams_depth >= 0.4 m`
  - cause: not visible to any current check (structure or logic differs)
