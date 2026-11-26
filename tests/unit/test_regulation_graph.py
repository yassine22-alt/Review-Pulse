"""The regulation graph: references, definitions, tables and exceptions resolved by rules, in four languages, moved and renumbered."""

from __future__ import annotations

import pytest

from reviewpulse.regs import build_graph, load_cues, resolve_context
from reviewpulse.regs import synthetic as S
from reviewpulse.rules.clauses import split_text


def graph_of(text: str, **kw):
    return build_graph(text, split_text(text), **kw)


def f1(gold: set, got: set) -> tuple[float, float]:
    tp = len(gold & got)
    return (tp / len(got) if got else 1.0), (tp / len(gold) if gold else 1.0)


@pytest.mark.parametrize("lang", ["en", "fr", "de", "es"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_planted_structure_is_found(lang, seed):
    cl = S.build(5, 5, seed=seed)
    text = S.render(cl, lang)
    got = S.edges_by_marker(graph_of(text))
    precision, recall = f1(S.gold(cl), got)
    assert recall >= 0.95 and precision >= 0.95, (lang, sorted(S.gold(cl) - got), sorted(got - S.gold(cl)))


@pytest.mark.parametrize("lang", ["en", "fr", "de", "es"])
def test_renumbered_and_moved_documents_give_the_same_edges(lang):
    cl = S.build(5, 5, seed=4)
    base = S.edges_by_marker(graph_of(S.render(cl, lang)))
    labels = {k: f"{int(v.split('.')[0]) + 40}.{v.split('.')[1]}" for k, v in S.labels_default(cl).items()}
    renumbered = S.edges_by_marker(graph_of(S.render(cl, lang, labels=labels, kw_shift=1)))
    order = [c.k for s in range(5, 0, -1) for c in cl if c.section == s]
    moved_labels = {}
    for i, sec in enumerate(range(5, 0, -1), 1):
        for j, c in enumerate([c for c in cl if c.section == sec], 1):
            moved_labels[c.k] = f"{i}.{j}"
    moved = S.edges_by_marker(graph_of(S.render(cl, lang, labels=moved_labels, order=order)))
    assert renumbered == base
    assert moved == base


def test_references_to_other_documents_and_to_nothing_are_not_resolved():
    text = ("1.1 K01 The stair must have a handrail as required by Regulation 7 of the Building Regulations 2010.\n\n"
            "1.2 K02 The stair must be lit (see paragraph 99.9).\n\n"
            "1.3 K03 The stair must be wide, see paragraph 1.2.\n")
    g = graph_of(text)
    st = {e.cited.lower(): e.status for e in g.edges if e.origin == "ref"}
    assert st["regulation 7"] == "external"
    assert st["paragraph 99.9"] == "unresolved"
    assert any(e.provider == "1.2" and e.consumer == "1.3" for e in g.edges)


def test_context_carries_spans_cues_and_reasons():
    cl = S.build(5, 5, seed=1)
    text = S.render(cl, "en")
    g = graph_of(text)
    for c in g.clauses:
        ctx = resolve_context(g, c.id)
        for lk in ctx.links():
            a, b = lk.source_span
            assert text[a:b] == lk.quote
            assert c.start <= a < b <= c.end
            ta, tb = lk.target_span
            assert 0 <= ta < tb <= len(text)
            assert lk.reason
    with_exc = [resolve_context(g, c.id) for c in g.clauses if resolve_context(g, c.id).exceptions]
    assert with_exc and all(lk.cue for x in with_exc for lk in x.exceptions)


def test_exception_directions():
    text = ("4.1 K01 A door must be fire resisting, except as provided in 4.2.\n\n"
            "4.2 K02 Doors to cupboards need not be fire resisting.\n\n"
            "4.3 K03 Notwithstanding 4.1, doors of a flat may be of any kind.\n")
    g = graph_of(text)
    ctx1 = resolve_context(g, "4.1")
    assert {lk.target_clause for lk in ctx1.exceptions} >= {"4.2", "4.3"}     # one cited by 4.1, one that overrides 4.1
    ctx3 = resolve_context(g, "4.3")
    assert not [lk for lk in ctx3.exceptions if lk.target_clause == "4.1"]


def test_exception_paragraphs_attach_to_the_clause_before():
    text = ("206.2 Employee work areas. Common use circulation paths shall be accessible.\n\n"
            "Exception 1. Modular furniture is not required to be accessible.\n\n"
            "206.3 Location. Routes shall coincide with the circulation path.\n")
    g = graph_of(text)
    ctx = resolve_context(g, "206.2")
    assert ctx.exceptions, g.stats()
    assert "Modular furniture" in ctx.exceptions[0].target_text


def test_definitions_travel_with_the_clauses_that_use_the_term():
    cl = S.build(5, 5, seed=2)
    text = S.render(cl, "en")
    g = graph_of(text)
    users = [c for c in cl if ("use",) in c.links]
    assert users
    defn = next(c for c in cl if c.kind == "definition")
    mk = S.markers(g)
    inv = {v: k for k, v in mk.items()}
    for u in users:
        ctx = resolve_context(g, inv[f"K{u.k:02d}"])
        assert [lk for lk in ctx.definitions if lk.target_clause == inv[f"K{defn.k:02d}"]], u.k


def test_glossary_entries_become_definitions():
    text = ("Definitions\n\n"
            "Accessible route. A continuous path that complies with this part and is free of steps.\n\n"
            "Habitable room. A room used for living, sleeping or eating, not a bathroom or a hall.\n\n"
            "5.1 An accessible route shall connect each habitable room to the entrance.\n")
    g = graph_of(text)
    assert {"accessible route", "habitable room"} <= set(g.terms)
    ctx = resolve_context(g, "5.1")
    assert len(ctx.definitions) == 2


def test_table_reference_brings_the_table_and_its_rows():
    text = ("3.1 K01 Travel distance must not exceed the limits in Table 3.2.\n\n"
            "Table 3.2 Maximum travel distance\n\n"
            "| Use | Distance |\n|---|---|\n| Flat | 9 m |\n| House | 18 m |\n\n"
            "3.3 K03 Another clause.\n")
    g = graph_of(text)
    ctx = resolve_context(g, "3.1")
    assert ctx.tables and ctx.tables[0].type == "table_of"
    assert "Flat" in ctx.tables[0].target_text


def test_a_new_language_needs_only_words_not_code():
    text = ("1.1 K01 La scala deve avere un corrimano, tranne quanto previsto al paragrafo 1.2.\n\n"
            "1.2 K02 Le scale esterne sono esenti.\n")
    base = graph_of(text)
    assert not [e for e in base.edges if e.type == "exception_of" and e.origin == "ref"]
    extra = {"exception_cues": ["tranne quanto previsto al"], "kinds": {"paragraph": ["paragrafo"]}}
    g = graph_of(text, cues=load_cues(extra=extra))
    assert [e for e in g.edges if e.type == "exception_of" and e.provider == "1.2" and e.consumer == "1.1"]


def test_baseline_regex_finds_less_than_the_graph():
    import re

    cl = S.build(5, 5, seed=0)
    text = S.render(cl, "de")
    n_baseline = len(re.findall(r"\bSection\s+\d", text))
    n_graph = len([e for e in graph_of(text).edges if e.origin == "ref" and e.provider])
    assert n_graph > 3 * max(n_baseline, 1)


def test_listing_clauses_do_not_create_references():
    text = ("1.1 K01 The stair is described in 2.1.\n\n"
            "Index\n\nStairs 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7\nDoors see paragraph 3.1, paragraph 3.2, paragraph 3.3, paragraph 3.4, paragraph 3.5\n")
    g = graph_of(text)
    assert len([e for e in g.edges if e.origin == "ref"]) <= 2
