"""The 46 development obligations. Frozen labels never become model examples."""
from pathlib import Path

from real_interpreter_holdout import access_graph, clause_context, fire_inputs, read, sources
from thermal_holdout import catalogue, contexts

from reviewpulse.factgraph.convert import to_inputs


def load_cases(repo: Path, access_text: Path) -> list[dict]:
    manifest, items = sources(repo, access_text)
    fire = read(repo / "reports/morocco-holdout-labels.json")
    access = read(repo / "reports/accessibility-holdout-labels.json")
    graph = access_graph(access)
    inputs = {"fire": (fire_inputs(fire["plans"]["A"]), None), "access": (to_inputs(graph), graph)}
    cases = [
        {"id": key, "suite": suite, "context": clause_context(manifest, items, suite, key),
         "inputs": inputs[suite][0], "graph": inputs[suite][1]}
        for suite in ("fire", "access") for key in items[suite]
    ]
    thermal = read(repo / "reports/thermal-holdout-labels.json")
    cases += [
        {"id": key, "suite": "thermal", "context": context, "inputs": catalogue(thermal), "graph": None}
        for key, context in contexts(read(repo / "reports/thermal-holdout-source.json")).items()
    ]
    return cases
