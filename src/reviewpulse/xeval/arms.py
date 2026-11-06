"""E4 arms: each adds one change to the one before, so a difference in score has one cause.

  baseline          interpreter's drafter, unchanged
  rec_ex            recursive schema + the same worked example the flat prompt has + offsets computed by code
  flat              flat node table (E1), same worked example
  flat_cat          flat + schema built from the item's own catalogue (fact and collection names are enums)
  flat_cat_repair   flat_cat + one repair attempt that shows the model the checker's error
"""

from __future__ import annotations

import json
import time

from ..interpreter.schema import Program
from ..interpreter.validate import validate_program
from . import drafters
from .drafters import BASE_SYSTEM, FLAT_SYSTEM, Draft, _classify, _payload, context_for, fix_spans
from .flat import FlatProgram, compile_flat
from .synth import binary, fact, lit, setop
from .verify import blocking, verify
from .world import bindings_of

ARMS_E4 = ("baseline", "rec_ex", "flat", "flat_cat", "flat_cat_repair")
VERIFY_ARM = "flat_cat_verify"

_EXAMPLE_TEXT = "Each shelter shall have a floor area of at least 7 m2"
_EXAMPLE = {
    "id": "r", "title": "shelter area", "document": "d",
    "requirement": setop("forall", "shelters", binary("ge", fact("shelters_area"), lit(7, "m2"))),
    "sources": [{"clause": "Art. 1", "start": 0, "end": len(_EXAMPLE_TEXT), "quote": _EXAMPLE_TEXT}],
}
REC_SYSTEM = (BASE_SYSTEM + chr(10) + 'Example (made-up facts), "' + _EXAMPLE_TEXT + '":' + chr(10)
              + json.dumps(_EXAMPLE))
REPAIR_NOTE = (chr(10) + "A previous attempt was rejected by an automatic checker. Fix ONLY the problem the "
               "checker names, keep everything else, and use only declared names.")


def flat_schema(cat: dict) -> dict:
    """The flat-program schema with fact names and collections limited to what the item declares."""
    schema = FlatProgram.model_json_schema()
    props = schema["$defs"]["FlatNode"]["properties"]
    props["name"] = {"anyOf": [{"enum": sorted(cat["bindings"])}, {"type": "null"}]}
    props["collection"] = {"anyOf": [{"enum": sorted(cat["collections"])}, {"type": "null"}]}
    return schema


def _flat_build(raw: dict, ctx, bindings, collections, check=None) -> Program:
    flat = FlatProgram.model_validate(raw)
    tree = compile_flat(flat, ctx.document)
    tree["sources"] = fix_spans([s.model_dump() for s in flat.sources], ctx)
    program = Program.model_validate(tree)
    validate_program(program, bindings, collections)
    if check is not None:
        issues = blocking(check(program))
        if issues:
            raise ValueError("verifier: " + "; ".join(i.message for i in issues))
    return program


def draft_arm(arm: str, item, client) -> Draft:
    if arm in drafters.ARMS:
        return drafters.draft(arm, item, client)
    if arm == "expr_vote":
        from .expr_arms import draft_vote

        return draft_vote(arm, item, client)
    if arm.startswith("expr"):
        from .expr_arms import draft_expr

        return draft_expr(arm, item, client)
    if arm == "rec_verify":
        from .expr_arms import draft_rec

        return draft_rec(arm, item, client)
    ctx, cat = context_for(item), item.catalogue
    bindings, collections = bindings_of(cat), list(cat["collections"])
    t0, raw = time.time(), None
    try:
        if arm == "rec_ex":
            raw = client.complete(REC_SYSTEM, _payload(ctx, cat), Program.model_json_schema())
            raw["sources"] = fix_spans(raw.get("sources", []), ctx)
            program = Program.model_validate(raw)
            program.status, program.approved_by, program.document = "draft", None, ctx.document
            validate_program(program, bindings, collections)
            return Draft(arm, program, "ok", "", time.time() - t0, raw)
        schema = flat_schema(cat)
        user = _payload(ctx, cat)
        raw = client.complete(FLAT_SYSTEM, user, schema)
        check = (lambda prog: verify(prog, item.text, cat, getattr(item, "lang", None))) if arm == VERIFY_ARM else None
        try:
            return Draft(arm, _flat_build(raw, ctx, bindings, collections, check), "ok", "", time.time() - t0, raw)
        except Exception as exc:  # noqa: BLE001
            if arm not in ("flat_cat_repair", VERIFY_ARM):
                raise
            first = f"{type(exc).__name__}: {str(exc)[:300]}"
        # one repair attempt, shown the checker's own message
        again = user + chr(10) + "PREVIOUS_DRAFT:" + json.dumps(raw) + chr(10) + "CHECKER_ERROR: " + first
        raw2 = client.complete(FLAT_SYSTEM + REPAIR_NOTE, again, schema)
        try:
            program = _flat_build(raw2, ctx, bindings, collections, check)
        except Exception as exc:  # noqa: BLE001
            stage = "verify" if str(exc).startswith("verifier:") else _classify(exc)
            return Draft(arm, None, stage, f"after repair: {type(exc).__name__}: {str(exc)[:250]}",
                         time.time() - t0, raw2, repaired=True)
        return Draft(arm, program, "ok", "repaired: " + first[:200], time.time() - t0, raw2, repaired=True)
    except Exception as exc:  # noqa: BLE001
        stage = "verify" if str(exc).startswith("verifier:") else _classify(exc)
        return Draft(arm, None, stage, f"{type(exc).__name__}: {str(exc)[:300]}", time.time() - t0, raw)
