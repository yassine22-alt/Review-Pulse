"""Adapt existing scripted test references to the typed drafting wire format."""
import json
from functools import wraps

from reviewpulse.interpreter.schema import Binding, Program
from reviewpulse.interpreter.structured import slots_from_program
from reviewpulse.xeval.expr_ir import compile_expr_program


def slot_response(method):
    @wraps(method)
    def complete(self, system, user, schema):
        structured = "nodes" in schema.get("properties", {})
        fixture_schema = schema
        if structured:
            fixture_schema = {**schema, "properties": {**schema["properties"], "require": {"type": "string"}}}
        raw = method(self, system, user, fixture_schema)
        if not structured or not isinstance(raw, dict) or "require" not in raw:
            return raw
        payload = json.loads(user)
        catalogue = payload["catalogue"]
        tree = compile_expr_program(
            raw, "fixture", {name: Binding.model_validate(spec) for name, spec in catalogue["bindings"].items()},
            {catalogue.get("whole", "building"), *catalogue.get("boundaries", [])},
            kinds=catalogue.get("kinds"), passable=catalogue.get("passable"),
            labels=catalogue.get("kind_labels"), groups=catalogue.get("groups"),
        )
        target = next(clause for clause in payload["clauses"] if clause["id"] == payload["target"])
        return slots_from_program(Program.model_validate(tree), target["text"].splitlines()[0].strip())

    return complete
