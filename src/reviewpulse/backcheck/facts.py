"""Fact graph attributes through the ledger, for the back check. Reading a sheet into a fact graph takes minutes (the full
pipeline), so this is opt in: `FactSource(old_pdf, new_pdf, cache_dir)` builds the graphs once per file and page and keeps them.

A door or room is found by its label (a schedule tag, a room name); its attribute (width_m, area_m2, ...) is asked of the
fact graph producers as a `FactRequest`, the same way the checks ask for it."""

from __future__ import annotations

import hashlib
from pathlib import Path

QUANTITY_ATTR = {"width": ("width_m",), "height": ("height_m",), "area": ("area_m2",), "distance": ("exit_distance_m",)}


def _file_id(pdf: str | Path) -> str:
    return hashlib.sha1(Path(pdf).read_bytes()).hexdigest()[:10]


def build_fact_graph(pdf: str | Path, page: int, cache_dir: str | Path):
    """The fact graph of one page (0 based) of a PDF, built by the pipeline and cached as JSON."""
    from ..factgraph import io as fgio

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{Path(pdf).stem}_{_file_id(pdf)}_p{page}.factgraph.json"
    if f.exists():
        return fgio.load(f)
    from .. import pipeline as P
    from ..factgraph.from_building import from_building
    from ..schema import BuildingModel, load

    stubs = P.inspect(pdf, runs_dir=cache / "runs", run_id=f"{Path(pdf).stem}_{_file_id(pdf)}")
    if not (stubs / f"building_{page}.json").exists():
        P.extract(stubs)
        P.build(stubs, images=False)
    fg = from_building(load(BuildingModel, stubs / f"building_{page}.json"))
    fgio.dump(fg, f)
    return fg


def node_value(fg, label: str, quantity: str):
    """The value of a quantity of the node labelled `label`, asked through the ledger's fact graph producers."""
    from ..ledger import FactRequest, fact_graph_producers

    wanted = QUANTITY_ATTR.get(quantity, ())
    for node in fg.nodes:
        if (node.label or "").strip().lower() != label.strip().lower():
            continue
        for attr in wanted:
            req = FactRequest(entity=node.id, fact=attr, unit="m2" if attr.endswith("m2") else "m")
            for prod in fact_graph_producers(fg):
                for cand in prod.answer(req):
                    if isinstance(cand.value, (int, float)) and cand.score > 0:
                        return float(cand.value), f"{cand.producer}:{node.id}"
    return None


def attribute_diff(fg_old, fg_new) -> list[str]:
    """Numbers and names that differ between two fact graphs, nodes paired by kind and label."""
    def index(fg):
        return {(n.kind, (n.label or "").strip().lower()): n for n in fg.nodes if n.label}
    a, b = index(fg_old), index(fg_new)
    out = []
    for key in sorted(set(a) & set(b)):
        for name in sorted(set(a[key].attrs) & set(b[key].attrs)):
            x, y = a[key].attrs[name].value, b[key].attrs[name].value
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
                if abs(x - y) > 0.005 * max(abs(x), abs(y), 1e-9):
                    out.append(f"{key[0]} {key[1]}: {name} {x:g} -> {y:g}")
            elif x != y:
                out.append(f"{key[0]} {key[1]}: {name} {x} -> {y}")
    out += [f"{k[0]} {k[1]} added" for k in sorted(set(b) - set(a))]
    out += [f"{k[0]} {k[1]} removed" for k in sorted(set(a) - set(b))]
    return out


class FactSource:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.pdfs: dict[str, str] = {}

    def value(self, side: str, pdf: str, page: int, tag: str, quantity: str):
        try:
            fg = build_fact_graph(pdf, page, self.cache_dir)
        except Exception:
            return None
        return node_value(fg, tag, quantity)
