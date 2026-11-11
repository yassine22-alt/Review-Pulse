"""The whole core path on something that is not a building: a water network described by a requirement document.

Clause -> checked rule (scripted model) -> judge -> findings -> coverage report, with no building model, no rooms, no doors,
no EXIT. If any part of the core assumed a building, this test would fail.
"""

from reviewpulse.factgraph.convert import to_catalogue, to_graph, to_inputs
from reviewpulse.factgraph.relations import derive_relations
from reviewpulse.factgraph.schema import Edge, FactGraph, Inventory, Node
from reviewpulse.interpreter.checked import checked_draft
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.schema import Binding, Fact, Program
from reviewpulse.report.coverage import build
from reviewpulse.rules.clauses import split_text

TEXT = ("Art. 1: Every tank reaches the outlet without passing through a valve.\n"
        "Art. 2: Every tank has at least one pipe connection.\n"
        "Art. 3: The network is painted blue.\n")
ANSWERS = {
    "Art. 1": ("forall components c where c.kind == 'tank': reaches(c, OUTLET, avoiding 'valve')",
               "Every tank reaches the outlet without passing through a valve"),
    "Art. 2": ("forall components c where c.kind == 'tank': c.links_pipe >= 1",
               "Every tank has at least one pipe connection"),
}


class Scripted:
    model = "scripted"

    def complete(self, system, user, schema):
        import json

        target = json.loads(user)["target"]
        if target in ANSWERS:
            require, quote = ANSWERS[target]
            return {"title": target, "applies_when": None, "unless": None, "require": require,
                    "sources": [{"clause": target, "quote": quote}], "unresolved": []}
        return {"title": target, "applies_when": None, "unless": None, "require": "forall components c: c.colour == 'blue'",
                "sources": [{"clause": target, "quote": "painted blue"}], "unresolved": ["colour is not provided"]}


def network() -> FactGraph:
    def kind(value):
        return {"kind": Fact(value=value, source="survey", trusted=True)}

    fg = FactGraph(
        bindings={"kind": Binding(kind="string", description="Component type")},
        nodes=[Node(id="t1", kind="component", label="Tank 1", attrs=kind("tank")),
               Node(id="v1", kind="component", label="Valve 1", attrs=kind("valve")),
               Node(id="t2", kind="component", label="Tank 2", attrs=kind("tank")),
               Node(id="OUTLET", kind="outlet", role="boundary"), Node(id="net", kind="network", role="whole")],
        edges=[Edge(id="e1", a="t1", b="v1", kind="pipe", trusted=True),
               Edge(id="e2", a="v1", b="OUTLET", kind="pipe", trusted=True),
               Edge(id="e3", a="t2", b="OUTLET", kind="pipe", trusted=True)],
        inventory={"component": Inventory(complete=True, trusted=True)}, graph_complete=True,
        value_labels={"kind": {"tank": ["tank", "tanks"], "valve": ["valve", "valves"]}}, passable=["pipe"])
    return derive_relations(fg)


def test_a_water_network_goes_through_the_whole_loop():
    fg = network()
    inputs, graph = to_inputs(fg), to_graph(fg)
    interpreted, results, findings = {}, [], []
    for clause in ("Art. 1", "Art. 2", "Art. 3"):
        context = assemble_context("network.md", TEXT, split_text(TEXT), clause)
        out = checked_draft(context, inputs, fg, Scripted())
        interpreted[clause] = out
        if out["status"] != "DRAFTED":
            continue
        program = Program.model_validate({**out["program"], "status": "approved", "approved_by": "K"})
        out["decision"], out["approved_program"] = {"state": "approved", "by": "K", "at": "now"}, out["program"]
        found, explained = to_findings(program, inputs, graph)          # no model, no locator: no outline
        findings += [f.model_dump(mode="json") for f in found]
        results.append({"clause": clause, "program_id": program.id, "outcome": explained.outcome,
                        "checked": explained.selected, "missing": explained.missing, "issues": []})
    assert interpreted["Art. 1"]["status"] == "DRAFTED" and interpreted["Art. 2"]["status"] == "DRAFTED"
    assert interpreted["Art. 3"]["status"] == "UNRESOLVED"
    fails = [f for f in findings if f["verdict"] == "FAIL"]
    assert [f["subject_ids"] for f in fails] == [["t1"]]          # tank 1 only reaches the outlet through the valve
    report = build({"name": "Network", "plan": "survey", "inventory_reviewed": True},
                   {"name": "network.md", "clauses": [{"id": c, "text": c} for c in ("Art. 1", "Art. 2", "Art. 3")]},
                   interpreted, results, findings, looked_for=["component"])
    status = {c["id"]: c["status"] for c in report["clauses"]}
    assert status == {"Art. 1": "violated", "Art. 2": "satisfied", "Art. 3": "not_checked"}
    assert report["summary"]["decided"] == 2


def test_units_of_any_domain_flow_through_drafting_checking_and_judging():
    """Volumes in litres, pressures in bar, times in minutes: facts declared in other units than the document uses."""
    import json

    from reviewpulse.factgraph.schema import Node

    def tank(name, volume_m3, pressure_pa, fill_s):
        facts = {"kind": Fact(value="tank", source="survey", trusted=True),
                 "volume": Fact(value=volume_m3, source="survey", trusted=True),
                 "pressure": Fact(value=pressure_pa, source="survey", trusted=True),
                 "fill_time": Fact(value=fill_s, source="survey", trusted=True)}
        return Node(id=name, kind="component", label=name, attrs=facts)

    fg = FactGraph(
        bindings={"kind": Binding(kind="string", description="Component type"),
                  "volume": Binding(kind="number", unit="m3", description="Tank volume"),
                  "pressure": Binding(kind="number", unit="Pa", description="Working pressure"),
                  "fill_time": Binding(kind="number", unit="s", description="Time to fill the tank")},
        nodes=[tank("t1", 0.4, 150000, 600), tank("t2", 0.8, 300000, 3000), Node(id="net", kind="network", role="whole")],
        inventory={"component": Inventory(complete=True, trusted=True)}, graph_complete=True,
        value_labels={"kind": {"tank": ["tank", "tanks"]}})
    text = ("Art. 1: Every tank has a volume of at least 500 L.\n"
            "Art. 2: The working pressure of a tank is at most 2 bar.\n"
            "Art. 3: A tank fills in no more than 30 min.\n")
    answers = {"Art. 1": ("forall components c where c.kind == 'tank': c.volume >= 500 L", "a volume of at least 500 L"),
               "Art. 2": ("forall components c where c.kind == 'tank': c.pressure <= 2 bar", "at most 2 bar"),
               "Art. 3": ("forall components c where c.kind == 'tank': c.fill_time <= 30 min", "no more than 30 min")}

    class Model:
        model = "scripted"

        def complete(self, system, user, schema):
            clause = json.loads(user)["target"]
            require, quote = answers[clause]
            return {"title": clause, "applies_when": None, "unless": None, "require": require,
                    "sources": [{"clause": clause, "quote": quote}], "unresolved": []}

    inputs, graph = to_inputs(fg), to_graph(fg)
    outcomes = {}
    for clause in answers:
        context = assemble_context("hydro.md", text, split_text(text), clause)
        out = checked_draft(context, inputs, fg, Model())
        assert out["status"] == "DRAFTED", (clause, out["reason"])
        program = Program.model_validate({**out["program"], "status": "approved", "approved_by": "K"})
        _, explained = to_findings(program, inputs, graph)
        outcomes[clause] = (explained.outcome, [m.entity for m in explained.members if m.state == "violated"])
    assert outcomes["Art. 1"] == ("VIOLATED", ["t1"])       # 0.4 m3 = 400 L is under 500 L
    assert outcomes["Art. 2"] == ("VIOLATED", ["t2"])       # 300000 Pa = 3 bar is over 2 bar
    assert outcomes["Art. 3"] == ("VIOLATED", ["t2"])       # 3000 s = 50 min is over 30 min


def test_a_rule_reads_in_plain_words_from_the_facts_own_descriptions():
    from reviewpulse.xeval.expr_ir import compile_expr_program
    from reviewpulse.xeval.readback import describe_rule

    fg = network()
    bindings = {n: b.model_dump() for n, b in fg.bindings.items()}
    for n, b in list(fg.bindings.items()):
        bindings[n] = b.model_dump()
    tree = compile_expr_program(
        {"require": "forall components c where c.kind == 'tank': reaches(c, OUTLET, avoiding 'valve') and c.links_pipe >= 1",
         "sources": [{"clause": "1", "quote": "x"}]}, "d", fg.bindings, set(), kinds=to_catalogue(fg)["kinds"],
        passable=["pipe"])
    said = describe_rule(tree["requirement"], tree.get("applicability"), tree.get("exemption"), bindings, "net")["plain"]
    assert said.startswith("For every component where component type is tank:")
    assert "has a route to outlet without passing through valve" in said and "is at least 1" in said
