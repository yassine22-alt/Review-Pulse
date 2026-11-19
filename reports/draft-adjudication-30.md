# Assistant adjudication of 30 saved GPT-OSS drafts

Codex assistant, direct reading of source and saved drafts; NOT human or independent adjudication

Grade intent independent of grammar. correct requires full slot meaning, partly_correct flags incomplete/ambiguous meaning, wrong contradicts or omits slot. Numeric value and unit are separate; an omitted dimensional unit is partial, never silently correct. Whole intent is assessed against source, not merely fixture predicate. Not_applicable is excluded.

Full original model objects and old/new exact scores: [JSON](draft-adjudication-30.json). C=correct; P=partly correct; W=wrong; N=not applicable.

| Draft | Source (including supplied context) | Model requirement / applicability | Subject | Fact | Op | Value | Unit | Scope | Whole intent | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T01 monolithic | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≤ 0,65 &#124; | {"subject": "roof_u", "require": "roof_u <= 0.65", "applies_when": "approach == \"prescriptive\" and building_class == \"residential\" and climate_zone == \"Z3\"", "unless": null, "metadata_applicability": [{"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T01", "quote": "Approche prescriptive"}}, {"kind": "string", "field": "building_class", "operator": "eq", "value": "residential", "source": {"clause": "T01", "quote": "bâtiments résidentiels"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z3", "source": {"clause": "T01", "quote": "Z3"}}], "fact_declarations": []} | wrong | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right roof threshold; subject is a property, not a building. Unit omitted and glazing band missing. |
| T01 decomposed | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≤ 0,65 &#124; | {"subject": "bâtiments résidentiels (approche prescriptive)", "require": "roof_u <= 0.65", "applies_when": "building_class == \"residential\" and approach == \"prescriptive\" and climate_zone == \"Z3\"", "unless": null, "metadata_applicability": [{"kind": "string", "field": "building_class", "operator": "eq", "value": "residential", "source": {"clause": "T01 header", "quote": "&#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;"}}, {"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T01 header", "quote": "&#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z3", "source": {"clause": "T01", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≤ 0,65 &#124;"}}], "fact_declarations": []} | correct | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right threshold; band omitted and explicitly misconstrued as air-tightness. Unit implicit only. |
| T04 monolithic | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124; | {"subject": "slab_r", "require": "slab_r >= 0.75", "applies_when": "approach == \"prescriptive\" and building_class == \"residential\" and climate_zone == \"Z3\" and glazing_ratio >= 26 and glazing_ratio <= 35", "unless": null, "metadata_applicability": [{"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T04", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124;"}}, {"kind": "string", "field": "building_class", "operator": "eq", "value": "residential", "source": {"clause": "T04", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124;"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z3", "source": {"clause": "T04", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124;"}}, {"kind": "number", "unit": "%", "field": "glazing_ratio", "operator": "ge", "value": 26, "source": {"clause": "T04", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124;"}}, {"kind": "number", "unit": "%", "field": "glazing_ratio", "operator": "le", "value": 35, "source": {"clause": "T04", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124;"}}], "fact_declarations": []} | wrong | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right slab threshold. Global fact is named correctly; bare quantity lacks unit. Percent scope values lack percent units. |
| T04 decomposed | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z3 &#124; 26 – 35 % &#124; ≥ 0,75 &#124; | {"subject": "bâtiments résidentiels", "require": "slab_r >= 0.75", "applies_when": "approach == \"prescriptive\" and building_class == \"résidentiels\" and climate_zone == \"Z3\"", "unless": null, "metadata_applicability": [{"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T04 header", "quote": "&#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;"}}, {"kind": "string", "field": "building_class", "operator": "eq", "value": "résidentiels", "source": {"clause": "T04 header", "quote": "&#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z3", "source": {"clause": "T04 header", "quote": "&#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;"}}], "fact_declarations": []} | correct | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right threshold; glazing band missing, residential spelling differs. Unit omitted. |
| T06 monolithic | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124; | {"subject": "roof_u", "require": "roof_u <= 0.55", "applies_when": "approach == \"prescriptive\" and climate_zone == \"Z4\" and glazing_ratio >= 26 and glazing_ratio <= 35", "unless": null, "metadata_applicability": [], "fact_declarations": []} | wrong | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right roof threshold; building class missing. Scope numbers lack explicit percent units. |
| T06 decomposed | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des toitures exposées (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124; | {"subject": "Prescriptive approach for residential buildings", "require": "roof_u <= 0.55", "applies_when": "(building_class == \"résidentiel\") and (approach == \"prescriptive\") and (climate_zone == \"Z4\") and (glazing_ratio >= 26) and (glazing_ratio <= 35)", "unless": null, "metadata_applicability": [{"kind": "string", "field": "building_class", "operator": "eq", "value": "résidentiel", "source": {"clause": "T06", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124;"}}, {"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T06", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124;"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z4", "source": {"clause": "T06", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124;"}}, {"kind": "number", "field": "glazing_ratio", "operator": "ge", "value": 26, "source": {"clause": "T06", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124;"}}, {"kind": "number", "field": "glazing_ratio", "operator": "le", "value": 35, "source": {"clause": "T06", "quote": "&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≤ 0,55 &#124;"}}], "fact_declarations": []} | correct | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right threshold; translated class and percent band not fully normalized. Unit omitted. |
| T09 monolithic | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≥ 1,25 &#124; | {"subject": "building", "require": "floor_R >= 1.25", "applies_when": "approach == \"prescriptive\" and building_class == \"residential\" and climate_zone == \"Z4\" and glazing_ratio >= 26 and glazing_ratio <= 35", "unless": null, "metadata_applicability": [{"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T09 header", "quote": "&#124; Usage et approche &#124;"}}, {"kind": "string", "field": "building_class", "operator": "eq", "value": "residential", "source": {"clause": "T09 header", "quote": "&#124; Usage et approche &#124;"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z4", "source": {"clause": "T09", "quote": "&#124; Z4 &#124;"}}, {"kind": "number", "field": "glazing_ratio", "operator": "ge", "value": 26, "source": {"clause": "T09", "quote": "26 – 35 %"}}, {"kind": "number", "field": "glazing_ratio", "operator": "le", "value": 35, "source": {"clause": "T09", "quote": "26 – 35 %"}}], "fact_declarations": []} | partly_correct | partly_correct | correct | correct | partly_correct | partly_correct | partly_correct | floor_R is an undeclared alternative for slab resistance; unit omitted. Scope percent units omitted. |
| T09 decomposed | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; R des planchers sur sol (m²·K/W) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z4 &#124; 26 – 35 % &#124; ≥ 1,25 &#124; | {"subject": "building", "require": "building.slab_r >= 1.25", "applies_when": "building.approach == \"prescriptive\" and building.usage == \"résidentiels\" and building.climate_zone == \"Z4\"", "unless": null, "metadata_applicability": [{"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T09", "quote": "Approche prescriptive"}}, {"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z4", "source": {"clause": "T09", "quote": "Z4"}}], "fact_declarations": [{"kind": "number", "unit": "m2·K/W", "name": "slab_r", "entity": "building", "definition": "Thermal resistance R of floor slabs on ground", "source": {"clause": "T09", "quote": "≥ 1,25"}, "status": "proposed"}]} | partly_correct | correct | correct | correct | correct | partly_correct | partly_correct | Right slab fact/threshold and declared resistance unit. Building class and glazing band missing from metadata. |
| T13 monolithic | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des fenêtres (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z5 &#124; 26 – 35 % &#124; ≤ 2,60 &#124; | {"subject": "building", "require": "window_u <= 2.60", "applies_when": "(climate_zone == \"Z5\") and (glazing_ratio >= 26) and (glazing_ratio <= 35)", "unless": null, "metadata_applicability": [{"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z5", "source": {"clause": "T13", "quote": "Z5"}}, {"kind": "number", "field": "glazing_ratio", "operator": "ge", "value": 26, "source": {"clause": "T13", "quote": "26 – 35 %"}}, {"kind": "number", "field": "glazing_ratio", "operator": "le", "value": 35, "source": {"clause": "T13", "quote": "26 – 35 %"}}], "fact_declarations": []} | partly_correct | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right window threshold. Generic subject; class and approach missing from applicability. |
| T13 decomposed | &#124; Usage et approche &#124; Zone climatique &#124; TGBV &#124; U des fenêtres (W/m²/K) &#124;<br><br>&#124; Approche prescriptive, bâtiments résidentiels &#124; Z5 &#124; 26 – 35 % &#124; ≤ 2,60 &#124; | {"subject": "bâtiments résidentiels (approche prescriptive)", "require": "window_u <= 2.60", "applies_when": "approach == \"prescriptive\" and building_class == \"residential\"", "unless": null, "metadata_applicability": [{"kind": "string", "field": "climate_zone", "operator": "eq", "value": "Z5", "source": {"clause": "T13", "quote": "Z5"}}, {"kind": "number", "field": "glazing_ratio", "operator": "ge", "value": 26, "source": {"clause": "T13", "quote": "26 – 35 %"}}, {"kind": "number", "field": "glazing_ratio", "operator": "le", "value": 35, "source": {"clause": "T13", "quote": "26 – 35 %"}}, {"kind": "string", "field": "approach", "operator": "eq", "value": "prescriptive", "source": {"clause": "T13", "quote": "Approche prescriptive"}}], "fact_declarations": []} | correct | correct | correct | correct | partly_correct | partly_correct | partly_correct | Right window threshold; building class missing from metadata, bare percent bounds, unit omitted. |
| M03 monolithic | Rez-de-chaussée : 50 m si choix entre 2 sorties ; 30 m s’il existe une seule sortie. | {"subject": "travel", "require": "(count(building.exits where eligible) >= 2) => travel <= 50 and (count(building.exits where eligible) == 1) => travel <= 30", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | partly_correct | partly_correct | wrong | correct | partly_correct | wrong | wrong | Thresholds 50 and 30 retained, but two implications vacuously pass with zero exits; ground-floor scope absent. |
| M03 decomposed | Rez-de-chaussée : 50 m si choix entre 2 sorties ; 30 m s’il existe une seule sortie. | {"subject": "ground floor evacuation travel distance", "require": "travel <= 50", "applies_when": "count(exits) == 2", "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | partly_correct | partly_correct | correct | partly_correct | partly_correct | partly_correct | Only the two-exit/50m branch remains; single-exit/30m branch and eligibility filter lost. |
| M04 monolithic | Les portes des locaux accessibles au public donnant sur des dégagements en cul-de-sac ne doivent pas être à plus de 10 m du débouché de ce cul-de-sac. | {"subject": "door", "require": "travel <= 10", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | partly_correct | wrong | correct | correct | partly_correct | partly_correct | wrong | travel means overall evacuation travel, not door-to-dead-end junction distance. Subject under-specified. |
| M04 decomposed | Les portes des locaux accessibles au public donnant sur des dégagements en cul-de-sac ne doivent pas être à plus de 10 m du débouché de ce cul-de-sac. | {"subject": "portes des locaux accessibles au public donnant sur des dégagements en cul-de-sac", "require": "discharge <= 10", "applies_when": "subject == \"portes des locaux accessibles au public donnant sur des dégagements en cul-de-sac\"", "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | wrong | correct | correct | partly_correct | partly_correct | wrong | discharge is stair-to-exit distance, not dead-end distance. Correct number and comparator cannot rescue wrong fact. |
| M05 monolithic | La largeur minimale de chaque dégagement doit être calculée en fonction d'une largeur-type appelée « unité de passage » (UP), égale à 0,60 m. Toutefois, quand un dégagement ne comporte qu'une ou deux unités de passage, la largeur est respectivement portée de 0,60 m à 0,90 m et de 1,20 m à 1,40 m.<br><br>Les sorties, issues sont calculées en fonction des effectifs des personnes susceptibles de les emprunter selon les règles suivantes.<br><br>Des circulations horizontales de deux unités de passage au moins relient les dégagements entre eux : au rez-de-chaussée, les escaliers aux sorties et les sorties entre elles. | {"subject": "exits", "require": "forall e1 in exits, e2 in exits where e1 != e2: exists p in travel where p >= 2 * 0.60", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | wrong | wrong | wrong | wrong | partly_correct | wrong | wrong | Exit-pair distance replaces connector width and 2*0.60 ignores the explicit two-UP exception of 1.40m. |
| M05 decomposed | La largeur minimale de chaque dégagement doit être calculée en fonction d'une largeur-type appelée « unité de passage » (UP), égale à 0,60 m. Toutefois, quand un dégagement ne comporte qu'une ou deux unités de passage, la largeur est respectivement portée de 0,60 m à 0,90 m et de 1,20 m à 1,40 m.<br><br>Les sorties, issues sont calculées en fonction des effectifs des personnes susceptibles de les emprunter selon les règles suivantes.<br><br>Des circulations horizontales de deux unités de passage au moins relient les dégagements entre eux : au rez-de-chaussée, les escaliers aux sorties et les sorties entre elles. | {"subject": "circulations horizontales", "require": "horizontal_circulation.units >= 2", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | partly_correct | correct | correct | partly_correct | partly_correct | partly_correct | Two passage units understood, but no binding to connector, UP conversion or required stair/exit links. |
| M06 monolithic | Un escalier protégé doit aboutir directement sur l’extérieur ou à une distance maximale de 20 m vers une sortie. | {"subject": "protected_stair", "require": "(travel <= 20) or (direct_outside == true)", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | partly_correct | correct | correct | partly_correct | partly_correct | partly_correct | Both alternatives retained in intent, but travel binds the wrong distance and direct_outside is undeclared. |
| M06 decomposed | Un escalier protégé doit aboutir directement sur l’extérieur ou à une distance maximale de 20 m vers une sortie. | {"subject": "escalier protégé", "require": "travel <= 20", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | wrong | partly_correct | correct | partly_correct | partly_correct | wrong | Drops direct-outdoors alternative and uses overall travel instead of stair discharge. |
| M08 monolithic | Les portes de recoupement des circulations horizontales utilisées dans les deux sens pour gagner une sortie vers l’extérieur doivent obligatoirement s’ouvrir en va-et-vient. | {"subject": "door", "require": "two_way eq true", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | partly_correct | correct | correct | not_applicable | not_applicable | partly_correct | partly_correct | Two-way opening understood; generic door subject loses subdivision/use-in-both-directions restriction. |
| M08 decomposed | Les portes de recoupement des circulations horizontales utilisées dans les deux sens pour gagner une sortie vers l’extérieur doivent obligatoirement s’ouvrir en va-et-vient. | {"subject": "portes de recoupement des circulations horizontales", "require": "building.two_way == true", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | correct | correct | not_applicable | not_applicable | partly_correct | partly_correct | Matches fixture boolean, but whole source scope is not encoded: subdivision doors used both ways toward exits. |
| A01 monolithic | Le sol des cheminements créés ou aménagés, ne doit pas être meublé, ni recouvert de revêtement non lisse, sans obstacles pour les roues et les cannes. | {"subject": "building", "require": "forall room where room.room_type in [\"corridor\",\"lobby\"]: room.floor_surface == \"smooth\" and not exists obstacle where obstacle.location == room", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | wrong | partly_correct | partly_correct | not_applicable | not_applicable | wrong | wrong | Arbitrary corridor/lobby restriction; smooth/obstacle checks omit no-furnishing constraint. |
| A01 decomposed | Le sol des cheminements créés ou aménagés, ne doit pas être meublé, ni recouvert de revêtement non lisse, sans obstacles pour les roues et les cannes. | {"subject": "Le sol des cheminements créés ou aménagés", "require": "not (pathway.floor.is_furnished) and not (pathway.floor.has_non_smooth_cover) and not (pathway.floor.has_obstacles)", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | correct | correct | not_applicable | not_applicable | correct | correct | Source intent preserved as three negations; unsupported nested facts prevent execution. Frozen firm fact is not explicitly stated by this source. |
| A04 monolithic | Ce bateau est constitué d'un plan incliné (inférieur à 5%) perpendiculaire à la chaussée et de deux surfaces inclinées (inférieures à 5%) de raccordement au trottoir. | {"subject": "unknown", "require": "", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | wrong | wrong | wrong | wrong | wrong | wrong | wrong | No interpretation emitted; unknown subject, missing slopes and two side transitions. |
| A04 decomposed | Ce bateau est constitué d'un plan incliné (inférieur à 5%) perpendiculaire à la chaussée et de deux surfaces inclinées (inférieures à 5%) de raccordement au trottoir. | {"subject": "bateau", "require": "", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | wrong | wrong | wrong | wrong | partly_correct | wrong | Curb-cut subject retained but empty requirement loses all slopes and geometry. |
| A08 monolithic | Le nombre de sièges adaptés aux personnes handicapées dans les salles publiques est fixé à un siège sur vingt. | {"subject": "public rooms", "require": "public_room.adapted_seats >= public_room.total_seats / 20", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | correct | correct | correct | correct | correct | correct | Intended one-in-twenty ratio and public-room scope preserved; unbound owner prevents execution. Algebra differs harmlessly from frozen multiplication. |
| A08 decomposed | Le nombre de sièges adaptés aux personnes handicapées dans les salles publiques est fixé à un siège sur vingt. | {"subject": "nombre de sièges adaptés aux personnes handicapées dans les salles publiques", "require": "r.adapted_seats >= r.total_seats / 20", "applies_when": "forall rooms r where r.room_type in [\"corridor\",\"lobby\"]: true", "unless": null, "metadata_applicability": [{"kind": "string", "field": "room_type", "operator": "in", "value": ["corridor", "lobby"], "source": {"clause": "A08", "quote": "toutes les salles publiques"}}], "fact_declarations": [{"kind": "number", "unit": "count", "name": "adapted_seats", "entity": "room", "definition": "Number of seats adapted for disabled persons in a room", "source": {"clause": "A08", "quote": "sièges adaptés aux personnes handicapées"}, "status": "proposed"}, {"kind": "number", "unit": "count", "name": "total_seats", "entity": "room", "definition": "Total number of seats in a room", "source": {"clause": "A08", "quote": "nombre de sièges"}, "status": "proposed"}]} | correct | correct | correct | correct | correct | wrong | wrong | Ratio retained but public rooms narrowed without source support to corridor/lobby; quoted scope not in source. |
| A10 monolithic | Les dispositions architecturales et les aménagements des bâtiments publics ou à usage du public, notamment les administrations, les centres hospitaliers, les établissements scolaires, universitaires et de formation, doivent être munis au niveau de tous les espaces de circulation des ascenseurs obéissant aux normes en vigueur | {"subject": "building", "require": "forall rooms where room_type in [\"corridor\",\"lobby\"]: elevator_present == true", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | partly_correct | partly_correct | partly_correct | not_applicable | not_applicable | wrong | wrong | Presence alone omits standards compliance; unsupported narrowing to corridor/lobby. |
| A10 decomposed | Les dispositions architecturales et les aménagements des bâtiments publics ou à usage du public, notamment les administrations, les centres hospitaliers, les établissements scolaires, universitaires et de formation, doivent être munis au niveau de tous les espaces de circulation des ascenseurs obéissant aux normes en vigueur | {"subject": "Les dispositions architecturales et les aménagements des bâtiments publics ou à usage du public, notamment les administrations, les centres hospitaliers, les établissements scolaires, universitaires et de formation", "require": "forall space in rooms where space.room_type == \"corridor\" or space.room_type == \"lobby\": exists elevator in space where elevator.complies_with_norms == true", "applies_when": null, "unless": null, "metadata_applicability": [{"kind": "string", "field": "building_type", "operator": "eq", "value": "public", "source": {"clause": "A10", "quote": "bâtiments publics ou à usage du public"}}], "fact_declarations": []} | correct | correct | correct | not_applicable | not_applicable | wrong | wrong | Lift standards intent retained, but arbitrary corridor/lobby scope excludes other circulation spaces. |
| A13 monolithic | Les dispositions architecturales et les aménagements des bâtiments publics ou à usage du public, notamment les administrations, les centres hospitaliers, les établissements scolaires, universitaires et de formation, doivent être munis au niveau de tous les espaces de circulation des ascenseurs obéissant aux normes en vigueur et de passages ayant une largeur minimale de 2.00 m avec le degré de la pente d'une valeur de 12% au maximum en vue de faciliter l'usage et l'accès aux personnes handicapées,<br><br>Ces passages doivent être munis de rampes servant de main courante sur les deux côtés. | {"subject": "passage", "require": "passage.handrail_both_sides == true", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": [{"kind": "boolean", "name": "handrail_both_sides", "entity": "passage", "definition": "Indicates whether a passage is equipped with handrails on both sides", "source": {"clause": "A13", "quote": "Ces passages doivent être munis de rampes servant de main courante sur les deux côtés."}, "status": "proposed"}]} | correct | correct | correct | not_applicable | not_applicable | partly_correct | partly_correct | Both handrails expressed in proposed boolean; singleton owner lacks universal binding and full antecedent scope. |
| A13 decomposed | Les dispositions architecturales et les aménagements des bâtiments publics ou à usage du public, notamment les administrations, les centres hospitaliers, les établissements scolaires, universitaires et de formation, doivent être munis au niveau de tous les espaces de circulation des ascenseurs obéissant aux normes en vigueur et de passages ayant une largeur minimale de 2.00 m avec le degré de la pente d'une valeur de 12% au maximum en vue de faciliter l'usage et l'accès aux personnes handicapées,<br><br>Ces passages doivent être munis de rampes servant de main courante sur les deux côtés. | {"subject": "passages", "require": "passages must be equipped with ramps serving as handrails on both sides", "applies_when": null, "unless": null, "metadata_applicability": [], "fact_declarations": []} | correct | correct | correct | not_applicable | not_applicable | correct | correct | Prose preserves both-side handrails on referenced passages; not executable DSL. Context supplies passage antecedent. |

## Scorer disagreement

{
  "old": {
    "undercredits": 73,
    "overcredits": 0,
    "disagreements": [
      73,
      95
    ],
    "partly_correct_excluded": 43,
    "undercredit_rows": [
      [
        "T01",
        "monolithic",
        "fact"
      ],
      [
        "T01",
        "monolithic",
        "operator"
      ],
      [
        "T01",
        "monolithic",
        "value"
      ],
      [
        "T01",
        "decomposed",
        "subject"
      ],
      [
        "T01",
        "decomposed",
        "fact"
      ],
      [
        "T01",
        "decomposed",
        "operator"
      ],
      [
        "T01",
        "decomposed",
        "value"
      ],
      [
        "T04",
        "monolithic",
        "fact"
      ],
      [
        "T04",
        "monolithic",
        "operator"
      ],
      [
        "T04",
        "monolithic",
        "value"
      ],
      [
        "T04",
        "decomposed",
        "subject"
      ],
      [
        "T04",
        "decomposed",
        "fact"
      ],
      [
        "T04",
        "decomposed",
        "operator"
      ],
      [
        "T04",
        "decomposed",
        "value"
      ],
      [
        "T06",
        "monolithic",
        "fact"
      ],
      [
        "T06",
        "monolithic",
        "operator"
      ],
      [
        "T06",
        "monolithic",
        "value"
      ],
      [
        "T06",
        "decomposed",
        "subject"
      ],
      [
        "T06",
        "decomposed",
        "fact"
      ],
      [
        "T06",
        "decomposed",
        "operator"
      ],
      [
        "T06",
        "decomposed",
        "value"
      ],
      [
        "T09",
        "monolithic",
        "operator"
      ],
      [
        "T09",
        "monolithic",
        "value"
      ],
      [
        "T09",
        "decomposed",
        "fact"
      ],
      [
        "T09",
        "decomposed",
        "operator"
      ],
      [
        "T09",
        "decomposed",
        "value"
      ],
      [
        "T09",
        "decomposed",
        "unit"
      ],
      [
        "T13",
        "monolithic",
        "fact"
      ],
      [
        "T13",
        "monolithic",
        "operator"
      ],
      [
        "T13",
        "monolithic",
        "value"
      ],
      [
        "T13",
        "decomposed",
        "subject"
      ],
      [
        "T13",
        "decomposed",
        "fact"
      ],
      [
        "T13",
        "decomposed",
        "operator"
      ],
      [
        "T13",
        "decomposed",
        "value"
      ],
      [
        "M03",
        "monolithic",
        "value"
      ],
      [
        "M03",
        "decomposed",
        "subject"
      ],
      [
        "M03",
        "decomposed",
        "value"
      ],
      [
        "M04",
        "monolithic",
        "operator"
      ],
      [
        "M04",
        "monolithic",
        "value"
      ],
      [
        "M04",
        "decomposed",
        "subject"
      ],
      [
        "M04",
        "decomposed",
        "operator"
      ],
      [
        "M04",
        "decomposed",
        "value"
      ],
      [
        "M05",
        "decomposed",
        "subject"
      ],
      [
        "M05",
        "decomposed",
        "operator"
      ],
      [
        "M05",
        "decomposed",
        "value"
      ],
      [
        "M06",
        "monolithic",
        "subject"
      ],
      [
        "M06",
        "monolithic",
        "operator"
      ],
      [
        "M06",
        "monolithic",
        "value"
      ],
      [
        "M06",
        "decomposed",
        "subject"
      ],
      [
        "M06",
        "decomposed",
        "value"
      ],
      [
        "M08",
        "monolithic",
        "fact"
      ],
      [
        "M08",
        "decomposed",
        "subject"
      ],
      [
        "A01",
        "decomposed",
        "subject"
      ],
      [
        "A01",
        "decomposed",
        "fact"
      ],
      [
        "A01",
        "decomposed",
        "operator"
      ],
      [
        "A04",
        "decomposed",
        "subject"
      ],
      [
        "A08",
        "monolithic",
        "subject"
      ],
      [
        "A08",
        "monolithic",
        "fact"
      ],
      [
        "A08",
        "monolithic",
        "operator"
      ],
      [
        "A08",
        "monolithic",
        "value"
      ],
      [
        "A08",
        "monolithic",
        "unit"
      ],
      [
        "A08",
        "decomposed",
        "subject"
      ],
      [
        "A08",
        "decomposed",
        "fact"
      ],
      [
        "A08",
        "decomposed",
        "operator"
      ],
      [
        "A08",
        "decomposed",
        "value"
      ],
      [
        "A08",
        "decomposed",
        "unit"
      ],
      [
        "A10",
        "decomposed",
        "subject"
      ],
      [
        "A13",
        "monolithic",
        "subject"
      ],
      [
        "A13",
        "monolithic",
        "fact"
      ],
      [
        "A13",
        "monolithic",
        "operator"
      ],
      [
        "A13",
        "decomposed",
        "subject"
      ],
      [
        "A13",
        "decomposed",
        "fact"
      ],
      [
        "A13",
        "decomposed",
        "operator"
      ]
    ],
    "overcredit_rows": []
  },
  "new": {
    "undercredits": 26,
    "overcredits": 0,
    "disagreements": [
      26,
      95
    ],
    "partly_correct_excluded": 43,
    "undercredit_rows": [
      [
        "T09",
        "monolithic",
        "operator"
      ],
      [
        "T09",
        "monolithic",
        "value"
      ],
      [
        "T09",
        "decomposed",
        "fact"
      ],
      [
        "T09",
        "decomposed",
        "operator"
      ],
      [
        "T09",
        "decomposed",
        "value"
      ],
      [
        "T09",
        "decomposed",
        "unit"
      ],
      [
        "M03",
        "monolithic",
        "value"
      ],
      [
        "M03",
        "decomposed",
        "value"
      ],
      [
        "M05",
        "decomposed",
        "operator"
      ],
      [
        "M05",
        "decomposed",
        "value"
      ],
      [
        "M06",
        "monolithic",
        "operator"
      ],
      [
        "M06",
        "monolithic",
        "value"
      ],
      [
        "A01",
        "decomposed",
        "fact"
      ],
      [
        "A01",
        "decomposed",
        "operator"
      ],
      [
        "A08",
        "monolithic",
        "fact"
      ],
      [
        "A08",
        "monolithic",
        "operator"
      ],
      [
        "A08",
        "monolithic",
        "value"
      ],
      [
        "A08",
        "monolithic",
        "unit"
      ],
      [
        "A08",
        "decomposed",
        "fact"
      ],
      [
        "A08",
        "decomposed",
        "operator"
      ],
      [
        "A08",
        "decomposed",
        "value"
      ],
      [
        "A08",
        "decomposed",
        "unit"
      ],
      [
        "A13",
        "monolithic",
        "fact"
      ],
      [
        "A13",
        "monolithic",
        "operator"
      ],
      [
        "A13",
        "decomposed",
        "fact"
      ],
      [
        "A13",
        "decomposed",
        "operator"
      ]
    ],
    "overcredit_rows": []
  }
}

## Limitations

- No independent reviewer. User authorized assistant-only grading for now.
- Whole intended correctness does not mean executable or approvable.
- Scorer disagreement counted only on eligible, decisively correct/wrong grades; partial and absent scope annotations excluded.
- Subject alternatives are review-approved evaluation data, not production prompt or extraction rules.
- Re-scoring the audit is a development resubstitution result, not scorer generalization.
- Frozen A01 firm requirement is not explicit in provided source; A10 frozen true is an unsupported-placeholder, not a valid lift rule.

The sole retained M08 staged draft matches the fixture predicate but loses source applicability. Consequently 1/1 reviewed approvable drafts is incomplete against the source; the former 0/1 fixture-based error count must not be read as whole-rule precision. The three source-intent-correct drafts are not executable retained rules.
