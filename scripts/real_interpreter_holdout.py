"""Source-only local-model run. Gold meanings and labels never enter a prompt."""
import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from reviewpulse.interpreter.checked import checked_draft
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.schema import Inputs
from reviewpulse.rules.clauses import Clause
from reviewpulse.xeval.drafters import BoundedOllama


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sources(repo, access_text):
    manifest = read(repo / "reports/morocco-interpreter-source.json")
    access = " ".join(access_text.read_text(encoding="utf-8").split())
    items = {"fire": dict(manifest["fire"]["clauses"]), "access": {}}
    for key, start, end in manifest["access"]["anchors"]:
        a = access.index(start)
        b = access.index(end, a) + len(end)
        items["access"][key] = access[a:b]
    manifest["access"]["context"] = {
        "A13": items["access"]["A11"], "A14": items["access"]["A11"]
    }
    return manifest, items


def tokens(txt):
    clean = unicodedata.normalize("NFKD", txt.casefold())
    return re.findall(r"[^\W_]+", "".join(c for c in clean if not unicodedata.combining(c)))


def audit(repo, targets):
    phrases = defaultdict(set)
    for key, strings in targets.items():
        for value in strings:
            words = tokens(value)
            length = min(len(words), 9)
            if length >= 4:
                for at in range(len(words) - length + 1):
                    phrases[tuple(words[at:at + length])].add(key)
    lengths = sorted({len(phrase) for phrase in phrases})
    paths = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z", "src", "tests", "scripts", "docs", "reports", "data"]
    ).decode().split("\0")
    hits = defaultdict(set)
    for name in paths:
        if not name or name.startswith(("reports/morocco-", "reports/accessibility-holdout-", "docs/nov18-")):
            continue  # previously frozen evaluation labels/results are outside runtime inputs
        path = repo / name
        if path.suffix not in {".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".txt", ".csv", ".js"}:
            continue
        words = tokens(path.read_text(encoding="utf-8", errors="replace"))
        for length in lengths:
            for at in range(len(words) - length + 1):
                for key in phrases.get(tuple(words[at:at + length]), ()):
                    hits[key].add(name)
    return {key: sorted(files) for key, files in sorted(hits.items())}


FIRE_FACTS = {
    "travel": ("number", "m", "Distance de parcours au rez-de-chaussée"),
    "connector": ("number", "m", "Largeur libre du passage de liaison"),
    "door_width": ("number", "m", "Largeur de passage libre de la porte du dégagement normal"),
    "dead_end": ("number", "m", "Distance entre une porte et le carrefour du couloir sans issue"),
    "discharge": ("number", "m", "Distance entre le débouché de l’escalier protégé et la sortie"),
    "normal": ("boolean", "1", "Dégagement normal désigné"),
    "accessory": ("boolean", "1", "Présence d'un dégagement accessoire"),
    "two_way": ("boolean", "1", "Sens d’ouverture bidirectionnel de la porte de recoupement"),
    "eligible": ("boolean", "1", "Ce dégagement distinct est admissible pour l'évacuation"),
}


def fire_inputs(plan, reviewed=False):
    seen = dict(plan["observed"])
    if reviewed:
        seen.update(plan["reviewed"])
    exits = seen.pop("exits")

    def fact(value):
        return {"value": value, "trusted": value is not None, "source": "frozen plan observation"}

    return Inputs.model_validate({
        "bindings": {k: {"kind": kind, "unit": unit, "description": description}
                     for k, (kind, unit, description) in FIRE_FACTS.items()},
        "facts": {"building": {k: fact(seen.get(k)) for k in FIRE_FACTS if k != "eligible"},
                  **{f"e{i}": {"eligible": fact(x)} for i, x in enumerate(exits, 1)}},
        "collections": {"exits": {"items": [f"e{i}" for i in range(1, len(exits) + 1)],
                                  "trusted": True, "complete": reviewed}},
    })


def access_graph(label):
    from reviewpulse.factgraph.from_building import BINDINGS, room_labels
    from reviewpulse.factgraph.schema import FactGraph

    plan = label["observed_plan"]
    attrs = {k for node in plan["rooms"] + plan["doors"] for k in node if k not in ("id", "kind")}
    nodes = [
        {"id": node["id"], "kind": node["kind"],
         "attrs": {k: {"value": v, "source": "frozen plan observation", "trusted": True}
                   for k, v in node.items() if k in attrs}}
        for node in plan["rooms"] + plan["doors"]
    ]
    return FactGraph.model_validate({
        "provenance": {"producer": "frozen plan observations"},
        "bindings": {k: BINDINGS[k] for k in attrs},
        "nodes": nodes + [{"id": "building", "kind": "building", "role": "whole"},
                          {"id": "EXIT", "kind": "exit", "role": "boundary"}],
        "edges": [{"id": f"edge{i}", "a": a, "b": b, "kind": "door", "via": door, "trusted": True}
                  for i, (a, b, door) in enumerate(plan["edges"])],
        "inventory": {k: {"trusted": True, "complete": plan["complete"]} for k in ("room", "door")},
        "value_labels": {"room_type": room_labels({"corridor", "lobby"})},
        "graph_complete": plan["complete"],
    })


def bundle(doc, key, text, refs):
    pieces = [*refs.items(), (key, text)]
    clauses = []
    cursor = 0
    for cid, body in pieces:
        clauses.append(Clause(id=cid, heading="", text=body, page=0, start=cursor, end=cursor + len(body)))
        cursor += len(body) + 2
    return ContextBundle(document=doc, text="\n\n".join(b for _, b in pieces), clauses=clauses, target=key)


def clause_context(manifest, items, suite, key):
    refs = manifest[suite]["context"]
    if suite == "fire":
        refs = refs if key in {"M01", "M02", "M05", "M07"} else {}
    else:
        refs = {"passage-context": refs[key]} if key in refs else {}
    return bundle(manifest[suite]["document"], key, items[suite][key], refs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument("--request-timeout", type=float, default=240)
    parser.add_argument("--triage", action="store_true", help="enable the app's bulk-document triage")
    args = parser.parse_args()
    manifest, items = sources(args.repo, args.access_text)
    fire = read(args.repo / "reports/morocco-holdout-labels.json")
    access = read(args.repo / "reports/accessibility-holdout-labels.json")
    if args.audit:
        target = {c["id"]: [items[suite][c["id"]], c["meaning"]]
                  for suite, labels in (("fire", fire), ("access", access)) for c in labels["clauses"]}
        found = audit(args.repo, target)
        args.output.write_text(json.dumps(found, indent=2))
        print(found)
        return

    from reviewpulse.factgraph.convert import to_inputs

    # Verify all inputs before contacting the model. Each run is fresh (no cached completions).
    graph = access_graph(access)
    inputs = {"fire": (fire_inputs(fire["plans"]["A"]), None), "access": (to_inputs(graph), graph)}
    client = BoundedOllama(model=args.model, num_predict=args.max_tokens, timeout_s=args.request_timeout)
    if not client.available():
        sys.exit(f"Local {args.model} is unavailable")
    done = set()
    if args.output.exists():
        done = {json.loads(line)["id"] for line in args.output.read_text(encoding="utf-8").splitlines()}
    with args.output.open("a", encoding="utf-8") as stream:
        for suite in ("fire", "access"):
            for key in items[suite]:
                if key in done:
                    continue
                context = clause_context(manifest, items, suite, key)
                start = time.perf_counter()
                try:
                    result = checked_draft(context, *inputs[suite], client, triage=args.triage)
                except Exception as exc:
                    result = {"status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
                record = {"suite": suite, "id": key, "seconds": round(time.perf_counter() - start, 1),
                          "configured_model": args.model, "max_tokens": args.max_tokens,
                          "bulk_triage": args.triage, **result}
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                print(key, record["status"], record["seconds"], flush=True)


if __name__ == "__main__":
    main()
