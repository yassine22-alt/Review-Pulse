# Audit of all 69 expression-parse failures

Codex assistant; direct reading of every failed expression and source excerpts, no independent human review

| Primary cause | Count |
| --- | --- |
| wrong_operator_or_fact_naming | 35/69 |
| genuine_semantic_error | 17/69 |
| unsupported_construct | 17/69 |
| wrapper_or_formatting | 0/69 |

Logged changes: [32, 69]; passed the original parse stage: [5, 69]; retained after all gates: [0, 69].

| Draft | Primary cause | Reason | Replay terminal stage |
| --- | --- | --- | --- |
| T01 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T01 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| M03 monolithic | genuine_semantic_error | Implications can vacuously satisfy with zero exits, unlike the frozen branch disjunction. Arrow syntax also unsupported; not rewritten. | expression_parse |
| M03 decomposed | genuine_semantic_error | Single-exit 30m branch dropped; count has no bound variable and eligible filter omitted. | expression_parse |
| A08 monolithic | wrong_operator_or_fact_naming | Correct intended algebraic ratio, but public_room is an unbound entity. No entity binding invented. | expression_parse |
| M07 decomposed | wrong_operator_or_fact_naming | Bare door_width and undeclared table_width. Table lookup and applicability cannot be inferred by normalizer. | expression_parse |
| M01 monolithic | unsupported_construct | count collection where predicate lacks a bound variable; bare occupancy also illegal. No variable invented. | expression_parse |
| M01 decomposed | unsupported_construct | count(building.exits) is not a supported collection/binder expression. | expression_parse |
| M02 decomposed | unsupported_construct | Two count expressions lack bound variables; normal/accessory meanings require linking, not formatting repair. | expression_parse |
| M04 monolithic | genuine_semantic_error | travel is an existing but wrong measurement: dead-end door-to-junction distance required. | subject |
| M04 decomposed | genuine_semantic_error | discharge is an existing but wrong measurement; source is about a dead end, not a stair. | expression_parse |
| M05 monolithic | genuine_semantic_error | Exit-pair travel replaces connector width and 1.20 ignores two-UP 1.40 exception. Invalid forall-in syntax also present. | expression_parse |
| M05 decomposed | wrong_operator_or_fact_naming | Unbound horizontal_circulation and units fact; UP-to-width exception/relationship not compiled. | expression_parse |
| M06 monolithic | genuine_semantic_error | travel is wrong distance and direct_outside undeclared; cannot replace by discharge/direct_outdoors without semantic edit. | expression_parse |
| M06 decomposed | genuine_semantic_error | Wrong travel distance and dropped direct-outdoors alternative. | verifier |
| M08 monolithic | wrong_operator_or_fact_naming | Bare two_way and named eq instead of symbolic comparator; both losslessly canonicalizable. Missing full door scope persists. | subject |
| M09 monolithic | unsupported_construct | exists step where lacks collection and binder; isolated-step inventory not in catalogue. | expression_parse |
| M09 decomposed | unsupported_construct | Natural-language obligation instead of executable expression; no prose-to-code substitution. | expression_parse |
| M10 monolithic | unsupported_construct | Natural-language fire-resistance alternatives need material/structure facts, not surface rewrite. | expression_parse |
| M10 decomposed | unsupported_construct | Natural-language alternative resistance requirement, not grammar. | expression_parse |
| M11 monolithic | unsupported_construct | Prose smoke extraction/protection predicate; unsupported facts and unresolved antecedent. | expression_parse |
| M11 decomposed | unsupported_construct | Prose must syntax with undeclared evacuation-route properties. | expression_parse |
| M12 monolithic | genuine_semantic_error | Color exclusions retained but transparency obligation omitted; door also unbound. | expression_parse |
| M13 decomposed | wrong_operator_or_fact_naming | Bare entity/fact/closes placeholders instead of declared domain facts. Cannot bind text labels as facts. | expression_parse |
| M14 monolithic | genuine_semantic_error | Specified-standard prose drops the explicit M1 class entirely. | expression_parse |
| M14 decomposed | unsupported_construct | Empty requirement; no parseable or substantive expression to normalize. | expression_parse |
| M15 monolithic | wrong_operator_or_fact_naming | Unbound walls/floors with coating facts not declared; material values retained. | expression_parse |
| M15 decomposed | wrong_operator_or_fact_naming | Bare cloisons/sols names not catalogue facts; material values retained. | expression_parse |
| A01 monolithic | genuine_semantic_error | Invented corridor/lobby restriction and omitted no-furnishing constraint; list-membership syntax also unsupported. | expression_parse |
| A01 decomposed | wrong_operator_or_fact_naming | Semantically plausible nested pathway.floor.* negations use unbound owner and unsupported property chain. | expression_parse |
| A02 monolithic | genuine_semantic_error | Invented slope threshold and door entity for a ramp requirement; unsupported implication also present. | expression_parse |
| A02 decomposed | unsupported_construct | Angle-bracket entity placeholders and unbound nested exists cannot be resolved by formatting. | expression_parse |
| A03 decomposed | wrong_operator_or_fact_naming | Sidewalk owner unbound; correct intended two-bound width interval. No collection invented. | expression_parse |
| A04 monolithic | unsupported_construct | Empty output with explicit unresolved declaration; no constraint emitted. | expression_parse |
| A04 decomposed | unsupported_construct | Empty requirement despite source slopes; no surface fix can recover omitted meaning. | expression_parse |
| A05 monolithic | genuine_semantic_error | Parking total divided by disabled population is not reserved spaces / all parking spaces. | expression_parse |
| A05 decomposed | genuine_semantic_error | Total >= 5% of itself is tautological and omits reserved-space numerator. | expression_parse |
| A06 monolithic | genuine_semantic_error | Invented corridor/lobby scope and 0.9m door threshold absent from source. | expression_parse |
| A06 decomposed | unsupported_construct | Natural-language practicable-route requirement instead of formal expression. | expression_parse |
| A07 decomposed | unsupported_construct | Missing count binders and unsupported includes syntax; scope precedence also requires review. | expression_parse |
| A10 monolithic | genuine_semantic_error | Presence-only lift predicate omits standards and arbitrarily narrows circulation spaces. | expression_parse |
| A10 decomposed | genuine_semantic_error | Arbitrary corridor/lobby restriction; malformed forall/exists-in binders cannot justify narrowed scope. | expression_parse |
| A12 monolithic | genuine_semantic_error | Changes universal direction-change landing obligation to one existential arbitrary corridor/lobby rest area. | expression_parse |
| A13 decomposed | unsupported_construct | Prose handrail requirement preserves intent but no executable structure. | expression_parse |
| A14 decomposed | wrong_operator_or_fact_naming | Unbound entrance_main and translated property names; percentages lack explicit units. No owner translation guessed. | expression_parse |
| A15 monolithic | unsupported_construct | Counts lack bound variables; phones/entries collections unavailable. Scope values are not linked. | expression_parse |
| T02 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T02 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T03 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T03 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T04 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T04 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T05 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T05 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T06 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T06 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T07 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T07 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T08 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T08 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | subject |
| T09 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T10 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T10 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T11 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T11 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | subject |
| T12 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T13 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T13 decomposed | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |
| T14 monolithic | wrong_operator_or_fact_naming | Bare global fact and/or bare metadata identifiers violate qualified-fact grammar; some use undeclared floor_R or solar_factor. Scope omissions and percent-unit errors may coexist. Only exact unambiguous catalogue ownership is normalized; no synonyms or metadata migration. | expression_parse |

## Limits

- Primary causes are mutually exclusive; naming and unsupported syntax often coexist with semantic errors. Counts are not semantic accuracy.
- No hosted regeneration, no weakening: no new quantifier, fact synonym, threshold, exception, variable or scope is invented.
- Global qualification applies only to exact facts owned exclusively by the catalogue global entity. Metadata conditions are never moved or dropped.
- Every normalization stores before/after and operations. Full source grounding, units, ownership, compiler round trip and verifier still run.
- Experimental archived-output replay only; production interpretation gates/defaults are unchanged.

Full unmodified outputs and normalization logs: [JSON](expression-parse-audit.json).
