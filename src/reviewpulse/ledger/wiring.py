"""How the ledger sits in the real review path: one switch, one entry point for the inputs, reviewer attestations on disk, and
the words a finding uses for a fact nobody could settle.

Switch: REVIEWPULSE_LEDGER=off keeps `factgraph.convert.to_inputs` (the path before the ledger). Measured on the 13 demo plans,
the ledger path gives the same `Inputs` as that function when one family answers each fact (docs/progress/M17).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..factgraph.convert import to_inputs
from ..factgraph.schema import FactGraph
from ..interpreter.schema import Inputs
from .adapters import Attestations
from .fuse import Resolution
from .inputs import ledger_inputs, requests_for_program

_TABLE_CACHE: dict[tuple, object] = {}


def ledger_enabled() -> bool:
    return os.environ.get("REVIEWPULSE_LEDGER", "on").strip().lower() != "off"


def _table_producers(model) -> list:
    """The sheet table reader as a producer for one plan sheet (cached per sheet: a project asks once per clause)."""
    from ..schedules.legacy import enabled

    if model is None or not enabled():
        return []
    key = (model.sheet.id, len(model.sheet.texts), len(model.elements))
    if key not in _TABLE_CACHE:
        from .sheet_tables import sheet_table_producer

        try:
            _TABLE_CACHE[key] = sheet_table_producer(model.sheet, model.elements)
        except Exception:  # noqa: BLE001 - an extra source; without it the fact graph answers alone
            _TABLE_CACHE[key] = None
        if len(_TABLE_CACHE) > 16:
            _TABLE_CACHE.pop(next(iter(_TABLE_CACHE)))
    producer = _TABLE_CACHE[key]
    return [producer] if producer is not None else []


def build_inputs(fg: FactGraph, attestations: Attestations | None = None, model=None) -> tuple[Inputs, list[Resolution]]:
    """The inputs of a review: through the ledger by default, the plain fact graph conversion when REVIEWPULSE_LEDGER=off
    (then no resolutions are returned and findings are worded as before)."""
    if not ledger_enabled():
        return to_inputs(fg), []
    return ledger_inputs(fg, attestations, extra=_table_producers(model))


# ---- reviewer attestations, kept next to the project --------------------------------------------------------------------


def _file(directory: Path) -> Path:
    return Path(directory) / "attestations.json"


def load_attestations(directory: Path) -> Attestations:
    store = Attestations()
    f = _file(directory)
    if f.exists():
        try:
            for e in json.loads(f.read_text(encoding="utf-8")):
                store.attest(e["entity"], e["fact"], e["value"], reviewer=e["reviewer"], source=e["source"], unit=e.get("unit", "1"))
        except (ValueError, KeyError, TypeError):
            pass            # a damaged file attests nothing; it never turns into a value
    return store


def save_attestations(directory: Path, store: Attestations) -> None:
    f = _file(directory)
    f.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"entity": e.entity, "fact": e.fact, "value": e.value, "unit": e.unit, "reviewer": e.reviewer, "source": e.source}
            for e in store.entries]
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def attest(directory: Path, entity: str, fact: str, value, *, reviewer: str, source: str, unit: str = "1") -> Attestations:
    """Record one reviewer answer (a name and a source are mandatory) and write it next to the project."""
    store = load_attestations(directory)
    store.attest(entity, fact, value, reviewer=reviewer, source=source, unit=unit)
    save_attestations(directory, store)
    return store


# ---- the words of a finding ---------------------------------------------------------------------------------------------


def reviewer_question(res: Resolution) -> str:
    """The follow up request of an unresolved fact as a sentence a reviewer can answer."""
    ask = res.followup()
    if ask is None:
        return ""
    unit = f" in {ask.unit}" if ask.kind == "number" and ask.unit not in ("1", "", None) else ""
    return f"What is the {ask.fact} of {res.entity}{unit}? Answer with a source and your name to settle it."


def unresolved_for(program, resolutions: list[Resolution], base: Inputs, subjects: list[str] | None = None, limit: int = 5) -> list[dict]:
    """The facts a rule reads that the ledger could not settle (conflict, unverified, unknown), each with what the ledger knows
    and the question that would settle it. `subjects` limits it to the entities a finding is about, when it has any."""
    names = {r.fact for r in requests_for_program(program, base)}
    out = []
    for res in resolutions:
        if res.decided or res.request.fact not in names:
            continue
        if subjects and res.entity not in subjects:
            continue
        out.append({"entity": res.entity, "fact": res.request.fact, "status": res.status, "explain": res.explain(),
                    "question": reviewer_question(res)})
        if len(out) >= limit:
            break
    return out
