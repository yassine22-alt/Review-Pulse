"""I2 - Function registry.

The only ``fn`` values a rule may use. The Judge implements them in
``reviewpulse.engine``; the Interpreter's drafting prompt lists them verbatim.
A unit test fails if a registered function has no implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fn:
    name: str
    args: str
    returns: str
    impl: str              # "module:function" inside reviewpulse.engine
    needs_scale: bool = False
    doc: str = ""


_FNS = [
    Fn("area_m2", "room", "number (m2)", "metric:fn_area_m2", True, "Net floor area of a room"),
    Fn("min_width_m", "room", "number (m)", "metric:fn_min_width_m", True, "Smallest local width (width profile)"),
    Fn("width_m", "door or window element", "number (m)", "metric:fn_width_m", True, "Clear width of an opening"),
    Fn("ratio", "two numbers", "number", "metric:fn_ratio", True, "Window area over floor area"),
    Fn("exists_path", "graph, from, to, via_edges, avoid", "bool + witness path", "traversal:fn_exists_path",
       False, "Reachability avoiding room types"),
    Fn("shortest_path_m", "graph, from, to", "length + path", "traversal:fn_shortest_path_m", True,
       "Travel distance from the farthest point of the room, walked around corners, door to door"),
    Fn("swing_with_escape", "graph, doors (exit | route)", "door side opened into", "traversal:fn_swing_with_escape",
       False, "Doors open in the direction of escape"),
    Fn("disjoint_paths", "graph, from, to", "count + paths", "traversal:fn_disjoint_paths", False,
       "Number of independent routes to exits"),
    Fn("count_exits", "graph", "count", "traversal:fn_count_exits", False, "Number of exit doors"),
    Fn("forbidden_link", "graph, pairs", "offending edges", "traversal:fn_forbidden_link", False,
       "Door or opening between forbidden room types"),
    Fn("dead_end_no_window", "graph, room", "bool", "traversal:fn_dead_end_no_window", False,
       "One-door room without a window"),
    Fn("sum_parts", "dimension chain", "parts, sum, stated total", "consistency:fn_sum_parts", False,
       "Dimension chain parts against the overall dimension"),
    Fn("drawn_vs_stated", "dimension", "drawn, stated", "consistency:fn_drawn_vs_stated", True,
       "Written length against drawn length"),
    Fn("stated_vs_computed_area", "room", "stated, computed", "consistency:fn_stated_vs_computed_area", True,
       "Area written in the room against computed area"),
    Fn("join", "plan tags, schedule, key", "matched, missing, unused, mismatches", "consistency:fn_join", False,
       "Plan tags against schedule rows"),
    Fn("programme_rooms", "rooms, brief rows", "count and area per room type", "consistency:fn_programme_rooms",
       False, "Rooms required by the brief: present, as many of each type, each at its area"),
    Fn("present", "items, required list", "missing list", "consistency:fn_present", False,
       "Presence of required items (labels, dimensions, title-block fields)"),
    Fn("swing_conflicts", "door elements", "conflicting pairs with overlap polygons", "swing:fn_swing_conflicts",
       True, "Overlapping door swings"),
    Fn("escape_window", "room", "best window width x height", "metric:fn_escape_window", True,
       "Room has an exterior window large enough to escape through (height from the schedule)"),
    Fn("isolated_rooms", "graph, room", "number of doors/openings", "traversal:fn_isolated_rooms", False,
       "Room with no door or opening"),
]

REGISTRY: dict[str, Fn] = {f.name: f for f in _FNS}


def resolve(name: str):
    import importlib

    mod, fn = REGISTRY[name].impl.split(":")
    return getattr(importlib.import_module(f"reviewpulse.engine.{mod}"), fn)


def prompt_table() -> str:
    """The function list as given to the drafting LLM (I4)."""
    return "\n".join(f"- {f.name}({f.args}) -> {f.returns}: {f.doc}" for f in _FNS)
