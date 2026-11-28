"""Audit of the normative form (src/reviewpulse/normative), without any label and without any model.

    python scripts/normative_audit.py [--out reports/m21_normative]

What is measured (all of it is metamorphic or planted, none of it needs a label):
  sentences  30 real sentences with a condition or an exception cue, taken from the split clauses of the real documents
             (reports/m14_split_cache2, same text as data/real_docs). THE TREES ARE HAND BUILT BY READING THE SENTENCES (by Khaoula's
             assistant in this session, not by any model). Each tree has hand written worlds with the outcome the sentence says.
             Checks: the tree validates, every node has a span whose quote is in the sentence, it compiles, the compiled
             program gives the outcome the sentence says in every hand world, and the round trip (tree to words to tree, in
             English, French and German) is equivalent.
  planted    every single node perturbation of those trees (swapped direction, swapped yes/no, wrong unit, wrong number, dropped
             exception, dropped condition, dropped alternative, "or" turned into "and", prohibition turned into obligation):
             the equivalence check must reject it. A perturbation that is NOT rejected is listed with its reason.
  readback   the same perturbations enter through a faulty reader of the words (the round trip): rejected? and does the repair list
             name the node that was perturbed?
  rules      the 10 labelled rule_now rules of benchmarks/checklist_labels.json: the rule the benchmark wrote (the expression in
             reports/benchmark_final/rows.jsonl, parsed by xeval/expr_ir.py) against a tree built by reading the sentence.
  relations  three relation sentences (no link or route node yet: the relation is a yes/no fact of the room).
  cue arm    how often the deterministic cue arm finds the condition and exception segments the hand trees contain.
  drafter    a scripted client that answers from the hand tree (an oracle, no model) drives the drafter on the sentences it can express.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reviewpulse.interpreter.schema import Binding, Program  # noqa: E402
from reviewpulse.normative import (  # noqa: E402
    Drafter,
    Exc,
    FactSpec,
    NormTree,
    Obligation,
    Scope,
    TemplateParser,
    all_of,
    any_of,
    compare_program,
    compare_program_all,
    compile_tree,
    cue_seeds,
    equivalent,
    leaf,
    roundtrip,
    run_tree,
    sp,
)
from reviewpulse.normative.equiv import _get, _set, _tokens  # noqa: E402
from reviewpulse.xeval.expr_ir import compile_expr_program  # noqa: E402

SAT, VIO, NA, EX, UNR = "SATISFIED", "VIOLATED", "NOT_APPLICABLE", "EXEMPT", "UNRESOLVED"


# ------------------------------------------------------------------------------------------------------------------ helpers
def B(name, label="", own="building", coll=None):
    return FactSpec(name=name, kind="boolean", owner=own, collection=coll, label={"en": label or name.replace("_", " ")})


def N(name, unit, label="", own="building", coll=None):
    return FactSpec(name=name, kind="number", unit=unit, owner=own, collection=coll, label={"en": label or name.replace("_", " ")})


def S(name, values, label="", own="building", coll=None):
    return FactSpec(name=name, kind="string", values=values, owner=own, collection=coll, label={"en": label or name.replace("_", " ")})


def case(cid, doc, clause, text, lang, facts, obs, checks, note=""):
    return {"id": cid, "doc": doc, "clause": clause, "text": text, "lang": lang, "facts": facts, "obs": obs, "checks": checks, "note": note}


def build(c) -> NormTree:
    return NormTree(clause_id=c["id"], text=c["text"], language=c["lang"], document=c["doc"], facts=c["facts"], obligations=c["obs"])


def sentences() -> list[dict]:
    out = []
    ada, adb, irc, fr, aqc = "ada_2010", "uk_adb_vol1_2019", "us_allentown_irc_checklist", "fr_caue_maisons", "fr_aqc_fiche_accessibilite"

    # ---------------- ADA
    t = "Where toe clearance is required at an element as part of a clear floor space, the toe clearance shall extend 17 inches (430 mm) minimum under the element."
    out.append(case("ada306.2.3", ada, "306.2.3", t, "en", [B("toe_required"), N("toe_depth", "m")], [Obligation(
        id="o1", applicability=leaf("toe_required", "eq", True, span=sp(t, "Where toe clearance is required at an element as part of a clear floor space")),
        requirement=leaf("toe_depth", "ge", 17, "in", sp(t, "17 inches (430 mm) minimum")), span=sp(t, t))],
        [({"toe_required": True, "toe_depth": 0.44}, [SAT]), ({"toe_required": True, "toe_depth": 0.4318}, [SAT]),
         ({"toe_required": True, "toe_depth": 0.40}, [VIO]), ({"toe_required": False, "toe_depth": 0.1}, [NA])]))

    t = "A single wheelchair space shall be 36 inches (915 mm) wide minimum Where two adjacent wheelchair spaces are provided, each wheelchair space shall be 33 inches (840 mm) wide minimum."
    out.append(case("ada802.1.2", ada, "802.1.2", t, "en", [B("adjacent_spaces"), N("space_width", "m")], [
        Obligation(id="o1", applicability=leaf("adjacent_spaces", "eq", False, span=sp(t, "A single wheelchair space")),
                   requirement=leaf("space_width", "ge", 36, "in", sp(t, "36 inches (915 mm) wide minimum")), span=sp(t, "A single wheelchair space shall be 36 inches (915 mm) wide minimum")),
        Obligation(id="o2", applicability=leaf("adjacent_spaces", "eq", True, span=sp(t, "Where two adjacent wheelchair spaces are provided")),
                   requirement=leaf("space_width", "ge", 33, "in", sp(t, "33 inches (840 mm) wide minimum")),
                   span=sp(t, "Where two adjacent wheelchair spaces are provided, each wheelchair space shall be 33 inches (840 mm) wide minimum"))],
        [({"adjacent_spaces": False, "space_width": 0.92}, [SAT, NA]), ({"adjacent_spaces": False, "space_width": 0.90}, [VIO, NA]),
         ({"adjacent_spaces": True, "space_width": 0.85}, [NA, SAT]), ({"adjacent_spaces": True, "space_width": 0.80}, [NA, VIO])],
        note="two atomic obligations in one clause"))

    t = "If the telephone or device is in a closed compartment, the compartment door hardware shall comply with 309."
    out.append(case("ada409.4.7.3", ada, "409.4.7.3", t, "en", [B("in_closed_compartment"), B("hardware_complies_309")], [Obligation(
        id="o1", applicability=leaf("in_closed_compartment", "eq", True, span=sp(t, "If the telephone or device is in a closed compartment")),
        requirement=leaf("hardware_complies_309", "eq", True, span=sp(t, "the compartment door hardware shall comply with 309")), span=sp(t, t))],
        [({"in_closed_compartment": True, "hardware_complies_309": True}, [SAT]), ({"in_closed_compartment": True, "hardware_complies_309": False}, [VIO]),
         ({"in_closed_compartment": False, "hardware_complies_309": False}, [NA])]))

    t = "Where storage is provided in accessible spaces, at least one of each type shall comply with 811."
    out.append(case("ada225.2", ada, "225.2", t, "en", [B("storage_provided"), B("one_of_each_type_complies_811")], [Obligation(
        id="o1", applicability=leaf("storage_provided", "eq", True, span=sp(t, "Where storage is provided in accessible spaces")),
        requirement=leaf("one_of_each_type_complies_811", "eq", True, span=sp(t, "at least one of each type shall comply with 811")), span=sp(t, t))],
        [({"storage_provided": True, "one_of_each_type_complies_811": True}, [SAT]), ({"storage_provided": True, "one_of_each_type_complies_811": False}, [VIO]),
         ({"storage_provided": False, "one_of_each_type_complies_811": False}, [NA])]))

    t = "Ramps not subject to the exception to 405.5 shall be designed to maintain a 36 inch (915 mm) minimum clear width when handrails are installed."
    out.append(case("ada505", ada, "505", t, "en", [B("exception_405_5_applies"), B("handrails_installed"), N("clear_width", "m")], [Obligation(
        id="o1", applicability=all_of(leaf("exception_405_5_applies", "eq", False, span=sp(t, "not subject to the exception to 405.5")),
                                      leaf("handrails_installed", "eq", True, span=sp(t, "when handrails are installed")), span=sp(t, "Ramps not subject to the exception to 405.5")),
        requirement=leaf("clear_width", "ge", 36, "in", sp(t, "36 inch (915 mm) minimum clear width")), span=sp(t, t))],
        [({"exception_405_5_applies": False, "handrails_installed": True, "clear_width": 0.92}, [SAT]),
         ({"exception_405_5_applies": False, "handrails_installed": True, "clear_width": 0.8}, [VIO]),
         ({"exception_405_5_applies": True, "handrails_installed": True, "clear_width": 0.5}, [NA]),
         ({"exception_405_5_applies": False, "handrails_installed": False, "clear_width": 0.5}, [NA])]))

    t = "Where provided, at least one of each type of depository, vending machine, change machine, and fuel dispenser shall comply with 309. EXCEPTION: Drive-up only depositories shall not be required to comply with 309."
    out.append(case("ada228.1", ada, "228.1", t, "en", [B("machines_provided"), B("one_of_each_type_complies_309"), B("drive_up_only_depository")], [Obligation(
        id="o1", applicability=leaf("machines_provided", "eq", True, span=sp(t, "Where provided")),
        requirement=leaf("one_of_each_type_complies_309", "eq", True, span=sp(t, "at least one of each type of depository, vending machine, change machine, and fuel dispenser shall comply with 309")),
        exceptions=[Exc(when=leaf("drive_up_only_depository", "eq", True, span=sp(t, "Drive-up only depositories")), cue="EXCEPTION", span=sp(t, "EXCEPTION: Drive-up only depositories shall not be required to comply with 309"))],
        span=sp(t, t))],
        [({"machines_provided": True, "one_of_each_type_complies_309": True, "drive_up_only_depository": False}, [SAT]),
         ({"machines_provided": True, "one_of_each_type_complies_309": False, "drive_up_only_depository": False}, [VIO]),
         ({"machines_provided": True, "one_of_each_type_complies_309": False, "drive_up_only_depository": True}, [EX]),
         ({"machines_provided": False, "one_of_each_type_complies_309": False, "drive_up_only_depository": False}, [NA])]))

    t = "An accessible route shall not be required between site arrival points and the building or facility entrance if the only means of access between them is a vehicular way not providing pedestrian access."
    out.append(case("ada_route_exc", ada, "Chapter 4 exception 2", t, "en", [B("accessible_route_provided"), B("only_vehicular_access")], [Obligation(
        id="o1", requirement=leaf("accessible_route_provided", "eq", True, span=sp(t, "An accessible route")),
        exceptions=[Exc(when=leaf("only_vehicular_access", "eq", True, span=sp(t, "the only means of access between them is a vehicular way not providing pedestrian access")),
                        cue="if", span=sp(t, "if the only means of access between them is a vehicular way not providing pedestrian access"))], span=sp(t, t))],
        [({"accessible_route_provided": True, "only_vehicular_access": False}, [SAT]), ({"accessible_route_provided": False, "only_vehicular_access": False}, [VIO]),
         ({"accessible_route_provided": False, "only_vehicular_access": True}, [EX]), ({"accessible_route_provided": True, "only_vehicular_access": True}, [EX])],
        note="the sentence itself is the exception: a route is required unless the only access is a vehicular way"))

    t = "Where solid partitions or security glazing separate visitors from detainees at least one of each type of cubicle or counter partition shall comply with 904.6."
    out.append(case("ada231.4.2", ada, "231.4.2", t, "en", [B("solid_partitions"), B("security_glazing"), B("one_of_each_type_complies_904_6")], [Obligation(
        id="o1", applicability=any_of(leaf("solid_partitions", "eq", True, span=sp(t, "solid partitions")), leaf("security_glazing", "eq", True, span=sp(t, "security glazing")),
                                      span=sp(t, "solid partitions or security glazing separate visitors from detainees")),
        requirement=leaf("one_of_each_type_complies_904_6", "eq", True, span=sp(t, "at least one of each type of cubicle or counter partition shall comply with 904.6")), span=sp(t, t))],
        [({"solid_partitions": True, "security_glazing": False, "one_of_each_type_complies_904_6": True}, [SAT]),
         ({"solid_partitions": False, "security_glazing": True, "one_of_each_type_complies_904_6": False}, [VIO]),
         ({"solid_partitions": False, "security_glazing": False, "one_of_each_type_complies_904_6": True}, [NA]),
         ({"solid_partitions": True, "security_glazing": True, "one_of_each_type_complies_904_6": False}, [VIO])]))

    t = "If existing elements, spaces, or common areas are altered, then each such altered element, space, or area shall comply with the applicable provisions of appendix A to this part."
    out.append(case("ada36.402", ada, "36.402 (2)", t, "en", [B("elements_altered"), B("altered_complies_appendix_a")], [Obligation(
        id="o1", applicability=leaf("elements_altered", "eq", True, span=sp(t, "If existing elements, spaces, or common areas are altered")),
        requirement=leaf("altered_complies_appendix_a", "eq", True, span=sp(t, "each such altered element, space, or area shall comply with the applicable provisions of appendix A to this part")),
        span=sp(t, t))],
        [({"elements_altered": True, "altered_complies_appendix_a": True}, [SAT]), ({"elements_altered": True, "altered_complies_appendix_a": False}, [VIO]),
         ({"elements_altered": False, "altered_complies_appendix_a": False}, [NA])]))

    # ---------------- ADB
    t = "If a garage is attached to or forms an integral part of a dwellinghouse, the garage should be separated from the rest of the dwellinghouse by fire resisting construction (minimum REI 30) (Diagram 5.1)."
    out.append(case("adb5.6", adb, "5.6", t, "en", [B("garage_attached"), B("garage_integral"), N("separation_rei", "min")], [Obligation(
        id="o1", applicability=any_of(leaf("garage_attached", "eq", True, span=sp(t, "a garage is attached to")), leaf("garage_integral", "eq", True, span=sp(t, "forms an integral part of a dwellinghouse")),
                                      span=sp(t, "a garage is attached to or forms an integral part of a dwellinghouse")),
        requirement=leaf("separation_rei", "ge", 30, "min", sp(t, "minimum REI 30")), span=sp(t, t))],
        [({"garage_attached": True, "garage_integral": False, "separation_rei": 30}, [SAT]), ({"garage_attached": False, "garage_integral": True, "separation_rei": 20}, [VIO]),
         ({"garage_attached": False, "garage_integral": False, "separation_rei": 0}, [NA]), ({"garage_attached": True, "garage_integral": True, "separation_rei": 29.99}, [VIO])],
        note="REI minutes written as 'REI 30': the unit minutes is read from the standard's notation"))

    t = "Smoke outlets connecting directly to the open air should be provided from every basement storey, except for any basement storey that has both of the following. a. A maximum floor area of 200m2. b. A floor a maximum of 3m below the adjacent ground level."
    out.append(case("adb16.3", adb, "16.3", t, "en", [B("smoke_outlet", own="member", coll="basements"), N("floor_area", "m2", own="member", coll="basements"),
                                                    N("depth_below_ground", "m", own="member", coll="basements")], [Obligation(
        id="o1", scope=Scope(collection="basements", variable="$s", span=sp(t, "every basement storey")),
        requirement=leaf("smoke_outlet", "eq", True, span=sp(t, "Smoke outlets connecting directly to the open air should be provided")),
        exceptions=[Exc(when=all_of(leaf("floor_area", "le", 200, "m2", sp(t, "A maximum floor area of 200m2")), leaf("depth_below_ground", "le", 3, "m", sp(t, "A floor a maximum of 3m below the adjacent ground level")),
                                    span=sp(t, "both of the following")), cue="except for", span=sp(t, "except for any basement storey that has both of the following"))], span=sp(t, t))],
        [({}, [UNR]), ({"basements": [{"smoke_outlet": True, "floor_area": 300, "depth_below_ground": 4}]}, [SAT]),
         ({"basements": [{"smoke_outlet": False, "floor_area": 300, "depth_below_ground": 4}]}, [VIO]),
         ({"basements": [{"smoke_outlet": False, "floor_area": 150, "depth_below_ground": 2}]}, [SAT]),
         ({"basements": [{"smoke_outlet": False, "floor_area": 200, "depth_below_ground": 3}]}, [SAT]),
         ({"basements": [{"smoke_outlet": False, "floor_area": 150, "depth_below_ground": 2}, {"smoke_outlet": False, "floor_area": 300, "depth_below_ground": 4}]}, [VIO]),
         ({"basements": [{"smoke_outlet": False, "floor_area": 150, "depth_below_ground": 3.5}]}, [VIO])],
        note="a member level exception: an excepted storey is not checked (shown as satisfied), not reported as exempt"))

    t = "If one element of structure supports or stabilises another, as a minimum the supporting element should have the same fire resistance as the other element."
    out.append(case("adb5.2", adb, "5.2", t, "en", [B("supports_another"), B("supporting_resistance_at_least_other")], [Obligation(
        id="o1", applicability=leaf("supports_another", "eq", True, span=sp(t, "If one element of structure supports or stabilises another")),
        requirement=leaf("supporting_resistance_at_least_other", "eq", True, span=sp(t, "the supporting element should have the same fire resistance as the other element")), span=sp(t, t))],
        [({"supports_another": True, "supporting_resistance_at_least_other": True}, [SAT]), ({"supports_another": True, "supporting_resistance_at_least_other": False}, [VIO]),
         ({"supports_another": False, "supporting_resistance_at_least_other": False}, [NA])]))

    t = "If smoke control is provided in the lobby, the travel distance can be increased to 7.5m maximum (see Diagram 3.7, example b)."
    out.append(case("adb_p32", adb, "P32", t, "en", [B("smoke_control_in_lobby"), N("travel_distance", "m")], [Obligation(
        id="o1", applicability=leaf("smoke_control_in_lobby", "eq", True, span=sp(t, "If smoke control is provided in the lobby")),
        requirement=leaf("travel_distance", "le", 7.5, "m", sp(t, "7.5m maximum")), span=sp(t, t))],
        [({"smoke_control_in_lobby": True, "travel_distance": 7.5}, [SAT]), ({"smoke_control_in_lobby": True, "travel_distance": 8}, [VIO]),
         ({"smoke_control_in_lobby": False, "travel_distance": 20}, [NA])], note="'can be increased to' is read as the upper limit that applies in that case"))

    t = "If travel distance is measured to a stair lobby, the lobby must not provide direct access to any storage room, flat or other space containing a fire hazard."
    out.append(case("adb_notes3", adb, "NOTES 3", t, "en", [B("measured_to_lobby"), B("access_to_storage_room"), B("access_to_flat"), B("access_to_fire_hazard_space")], [Obligation(
        id="o1", modality="prohibition", applicability=leaf("measured_to_lobby", "eq", True, span=sp(t, "If travel distance is measured to a stair lobby")),
        requirement=any_of(leaf("access_to_storage_room", "eq", True, span=sp(t, "any storage room")), leaf("access_to_flat", "eq", True, span=sp(t, "flat")),
                           leaf("access_to_fire_hazard_space", "eq", True, span=sp(t, "other space containing a fire hazard")), span=sp(t, "direct access to any storage room, flat or other space containing a fire hazard")),
        span=sp(t, t))],
        [({"measured_to_lobby": True, "access_to_storage_room": False, "access_to_flat": False, "access_to_fire_hazard_space": False}, [SAT]),
         ({"measured_to_lobby": True, "access_to_storage_room": False, "access_to_flat": True, "access_to_fire_hazard_space": False}, [VIO]),
         ({"measured_to_lobby": False, "access_to_storage_room": True, "access_to_flat": True, "access_to_fire_hazard_space": True}, [NA]),
         ({"measured_to_lobby": True, "access_to_storage_room": False, "access_to_flat": False, "access_to_fire_hazard_space": True}, [VIO])]))

    t = "Lift wells should comply with one of the following conditions. a. Be sited within the enclosures of a protected stairway. b. Be enclosed with fire resisting construction (minimum REI 30) when in a position that might prejudice the means of escape."
    out.append(case("adb3.99", adb, "3.99", t, "en", [B("in_protected_stairway"), N("enclosure_rei", "min")], [Obligation(
        id="o1", requirement=any_of(leaf("in_protected_stairway", "eq", True, span=sp(t, "Be sited within the enclosures of a protected stairway")),
                                    leaf("enclosure_rei", "ge", 30, "min", sp(t, "minimum REI 30")), span=sp(t, "one of the following conditions")), span=sp(t, t))],
        [({"in_protected_stairway": True, "enclosure_rei": 0}, [SAT]), ({"in_protected_stairway": False, "enclosure_rei": 30}, [SAT]), ({"in_protected_stairway": False, "enclosure_rei": 20}, [VIO])],
        note="alternatives; the condition 'when in a position that might prejudice the means of escape' on alternative b is NOT modelled"))

    # ---------------- IRC checklist (Allentown)
    rt = ["bedroom", "kitchen", "living", "office", "corridor", "bathroom"]
    t = "Habitable rooms must be min. 70 s.f. except kitchens, also min. 7' in any dimension. 304.1, 304.2"
    hab = lambda: any_of(*[leaf("room_type", "eq", v, span=sp(t, "Habitable rooms")) for v in ("bedroom", "kitchen", "living", "office")], span=sp(t, "Habitable rooms"))  # noqa: E731
    out.append(case("irc_item9", irc, "item 9", t, "en", [S("room_type", rt, own="member", coll="rooms"), N("area_m2", "m2", own="member", coll="rooms"), N("min_width_m", "m", own="member", coll="rooms")], [
        Obligation(id="o1", scope=Scope(collection="rooms", variable="$r", where=hab(), span=sp(t, "Habitable rooms")), requirement=leaf("area_m2", "ge", 70, "ft2", sp(t, "min. 70 s.f.")),
                   exceptions=[Exc(when=leaf("room_type", "eq", "kitchen", span=sp(t, "kitchens")), cue="except", span=sp(t, "except kitchens"))], span=sp(t, "Habitable rooms must be min. 70 s.f. except kitchens")),
        Obligation(id="o2", scope=Scope(collection="rooms", variable="$r", where=hab(), span=sp(t, "Habitable rooms")), requirement=leaf("min_width_m", "ge", 7, "ft", sp(t, "min. 7' in any dimension")),
                   span=sp(t, "also min. 7' in any dimension"))],
        [({"rooms": [{"room_type": "bedroom", "area_m2": 7, "min_width_m": 2.2}]}, [SAT, SAT]), ({"rooms": [{"room_type": "bedroom", "area_m2": 6, "min_width_m": 2.2}]}, [VIO, SAT]),
         ({"rooms": [{"room_type": "kitchen", "area_m2": 5, "min_width_m": 2.2}]}, [SAT, SAT]), ({"rooms": [{"room_type": "kitchen", "area_m2": 5, "min_width_m": 2.0}]}, [SAT, VIO]),
         ({"rooms": [{"room_type": "bathroom", "area_m2": 3, "min_width_m": 1.0}]}, [SAT, SAT]), ({"rooms": [{"room_type": "living", "area_m2": 6.5033, "min_width_m": 2.1336}]}, [SAT, SAT])],
        note="my reading: the 7 ft width applies to kitchens too; the benchmark rule excludes kitchens from both"))

    t = "Ceilings min. 7', except bathrooms, laundry rooms and non-habitable basements may be 6'8\". 305"
    rt2 = ["bedroom", "bathroom", "laundry", "basement_nonhabitable"]
    low = lambda: any_of(leaf("room_type", "eq", "bathroom", span=sp(t, "bathrooms")), leaf("room_type", "eq", "laundry", span=sp(t, "laundry rooms")),  # noqa: E731
                         leaf("room_type", "eq", "basement_nonhabitable", span=sp(t, "non-habitable basements")), span=sp(t, "bathrooms, laundry rooms and non-habitable basements"))
    out.append(case("irc_item10", irc, "item 10", t, "en", [S("room_type", rt2, own="member", coll="rooms"), N("ceiling_height_m", "m", own="member", coll="rooms")], [
        Obligation(id="o1", scope=Scope(collection="rooms", variable="$r", span=sp(t, "Ceilings")), requirement=leaf("ceiling_height_m", "ge", 7, "ft", sp(t, "min. 7'")),
                   exceptions=[Exc(when=low(), cue="except", span=sp(t, "except bathrooms, laundry rooms and non-habitable basements"))], span=sp(t, "Ceilings min. 7'")),
        Obligation(id="o2", scope=Scope(collection="rooms", variable="$r", where=low(), span=sp(t, "bathrooms, laundry rooms and non-habitable basements")),
                   requirement=leaf("ceiling_height_m", "ge", 80, "in", sp(t, "6'8\"")), span=sp(t, "bathrooms, laundry rooms and non-habitable basements may be 6'8\""))],
        [({"rooms": [{"room_type": "bedroom", "ceiling_height_m": 2.2}]}, [SAT, SAT]), ({"rooms": [{"room_type": "bedroom", "ceiling_height_m": 2.0}]}, [VIO, SAT]),
         ({"rooms": [{"room_type": "bathroom", "ceiling_height_m": 2.05}]}, [SAT, SAT]), ({"rooms": [{"room_type": "bathroom", "ceiling_height_m": 1.9}]}, [SAT, VIO]),
         ({"rooms": [{"room_type": "laundry", "ceiling_height_m": 2.032}]}, [SAT, SAT])], note="the weaker height for the excepted rooms is its own obligation"))

    t = "Stairways must have a light; three-way switch required at top and bottom if 6 or more risers. 303.7"
    out.append(case("irc_item8", irc, "item 8", t, "en", [B("stair_has_light"), N("risers", "1"), B("three_way_switch")], [
        Obligation(id="o1", requirement=leaf("stair_has_light", "eq", True, span=sp(t, "Stairways must have a light")), span=sp(t, "Stairways must have a light")),
        Obligation(id="o2", applicability=leaf("risers", "ge", 6, "1", sp(t, "6 or more risers")), requirement=leaf("three_way_switch", "eq", True, span=sp(t, "three-way switch required at top and bottom")),
                   span=sp(t, "three-way switch required at top and bottom if 6 or more risers"))],
        [({"stair_has_light": True, "risers": 5, "three_way_switch": False}, [SAT, NA]), ({"stair_has_light": True, "risers": 6, "three_way_switch": False}, [SAT, VIO]),
         ({"stair_has_light": False, "risers": 6, "three_way_switch": True}, [VIO, SAT])]))

    t = "Garage ceiling must be 5/8\" drywall if habitable rooms are above. Table 302.6"
    out.append(case("irc_item5", irc, "item 5", t, "en", [B("habitable_rooms_above"), N("drywall_thickness", "mm")], [Obligation(
        id="o1", applicability=leaf("habitable_rooms_above", "eq", True, span=sp(t, "if habitable rooms are above")), requirement=leaf("drywall_thickness", "ge", 0.625, "in", sp(t, "5/8\" drywall")),
        span=sp(t, "Garage ceiling must be 5/8\" drywall if habitable rooms are above"))],
        [({"habitable_rooms_above": True, "drywall_thickness": 16}, [SAT]), ({"habitable_rooms_above": True, "drywall_thickness": 12.7}, [VIO]),
         ({"habitable_rooms_above": False, "drywall_thickness": 0}, [NA]), ({"habitable_rooms_above": True, "drywall_thickness": 15.875}, [SAT])]))

    t = "Foundation wall must extend 6\" above finish grade (4\" if exterior wall is brick). 404.1.6"
    out.append(case("irc_item31", irc, "item 31", t, "en", [B("exterior_wall_brick"), N("extension_above_grade", "m")], [
        Obligation(id="o1", applicability=leaf("exterior_wall_brick", "eq", False, span=sp(t, "Foundation wall")), requirement=leaf("extension_above_grade", "ge", 6, "in", sp(t, "6\" above finish grade")),
                   span=sp(t, "Foundation wall must extend 6\" above finish grade")),
        Obligation(id="o2", applicability=leaf("exterior_wall_brick", "eq", True, span=sp(t, "if exterior wall is brick")), requirement=leaf("extension_above_grade", "ge", 4, "in", sp(t, "4\"")),
                   span=sp(t, "4\" if exterior wall is brick"))],
        [({"exterior_wall_brick": False, "extension_above_grade": 0.16}, [SAT, NA]), ({"exterior_wall_brick": False, "extension_above_grade": 0.12}, [VIO, NA]),
         ({"exterior_wall_brick": True, "extension_above_grade": 0.11}, [NA, SAT]), ({"exterior_wall_brick": True, "extension_above_grade": 0.09}, [NA, VIO])]))

    t = "Guards are required where open edge has a 30\" drop. 312.1"
    out.append(case("irc_item21", irc, "item 21", t, "en", [N("open_edge_drop", "m"), B("guard_provided")], [Obligation(
        id="o1", applicability=leaf("open_edge_drop", "ge", 30, "in", sp(t, "open edge has a 30\" drop")), requirement=leaf("guard_provided", "eq", True, span=sp(t, "Guards are required")), span=sp(t, "Guards are required where open edge has a 30\" drop"))],
        [({"open_edge_drop": 0.8, "guard_provided": True}, [SAT]), ({"open_edge_drop": 0.8, "guard_provided": False}, [VIO]), ({"open_edge_drop": 0.5, "guard_provided": False}, [NA]),
         ({"open_edge_drop": 0.762, "guard_provided": False}, [VIO])], note="'has a 30 inch drop' is read as 30 inches or more"))

    t = "Site should be graded away for 10' from the foundation unless a swale is built. 401.3"
    out.append(case("irc_item27", irc, "item 27", t, "en", [N("graded_away_distance", "m"), B("swale_built")], [Obligation(
        id="o1", requirement=leaf("graded_away_distance", "ge", 10, "ft", sp(t, "10' from the foundation")),
        exceptions=[Exc(when=leaf("swale_built", "eq", True, span=sp(t, "a swale is built")), cue="unless", span=sp(t, "unless a swale is built"))], span=sp(t, "Site should be graded away for 10' from the foundation unless a swale is built"))],
        [({"graded_away_distance": 3.1, "swale_built": False}, [SAT]), ({"graded_away_distance": 2.0, "swale_built": False}, [VIO]), ({"graded_away_distance": 2.0, "swale_built": True}, [EX]),
         ({"graded_away_distance": 3.048, "swale_built": False}, [SAT])]))

    t = "A CO detector is required outside each sleeping area if required by 315.2.1. 315.3"
    out.append(case("irc_item25", irc, "item 25", t, "en", [B("co_required_by_315_2_1"), B("co_detector_outside_sleeping_area")], [Obligation(
        id="o1", applicability=leaf("co_required_by_315_2_1", "eq", True, span=sp(t, "if required by 315.2.1")), requirement=leaf("co_detector_outside_sleeping_area", "eq", True, span=sp(t, "A CO detector is required outside each sleeping area")),
        span=sp(t, "A CO detector is required outside each sleeping area if required by 315.2.1"))],
        [({"co_required_by_315_2_1": True, "co_detector_outside_sleeping_area": True}, [SAT]), ({"co_required_by_315_2_1": True, "co_detector_outside_sleeping_area": False}, [VIO]),
         ({"co_required_by_315_2_1": False, "co_detector_outside_sleeping_area": False}, [NA])]))

    # ---------------- French (CAUE maisons, AQC)
    dk = ["interieure", "entree"]
    t = "- La largeur minimale des portes intérieures doit être de 0,80 mètre et présenter une largeur minimale de passage libre lorsque le vantail est ouvert à 90°, de 0,77 mètre."
    out.append(case("caue29", fr, "item 29", t, "fr", [S("door_kind", dk, own="member", coll="doors"), N("width", "m", own="member", coll="doors"), N("clear_width", "m", own="member", coll="doors")], [Obligation(
        id="o1", scope=Scope(collection="doors", variable="$d", where=leaf("door_kind", "eq", "interieure", span=sp(t, "portes intérieures")), span=sp(t, "portes intérieures")),
        requirement=all_of(leaf("width", "ge", 0.80, "m", sp(t, "0,80 mètre")), leaf("clear_width", "ge", 0.77, "m", sp(t, "0,77 mètre")), span=sp(t, "de 0,80 mètre et présenter une largeur minimale de passage libre lorsque le vantail est ouvert à 90°, de 0,77 mètre")),
        span=sp(t, t))],
        [({"doors": [{"door_kind": "interieure", "width": 0.85, "clear_width": 0.78}]}, [SAT]), ({"doors": [{"door_kind": "interieure", "width": 0.80, "clear_width": 0.70}]}, [VIO]),
         ({"doors": [{"door_kind": "interieure", "width": 0.75, "clear_width": 0.80}]}, [VIO]), ({"doors": [{"door_kind": "entree", "width": 0.5, "clear_width": 0.5}]}, [SAT])],
        note="'lorsque le vantail est ouvert' defines how the clear width is measured: not a condition of applicability"))

    t = "- La porte d’entrée doit avoir une largeur minimale de 0,90 mètre et une largeur minimale de passage libre lorsque le vantail est ouvert à 90°, de 0,83 mètre."
    out.append(case("caue28", fr, "item 28", t, "fr", [S("door_kind", dk, own="member", coll="doors"), N("width", "m", own="member", coll="doors"), N("clear_width", "m", own="member", coll="doors")], [Obligation(
        id="o1", scope=Scope(collection="doors", variable="$d", where=leaf("door_kind", "eq", "entree", span=sp(t, "porte d’entrée")), span=sp(t, "porte d’entrée")),
        requirement=all_of(leaf("width", "ge", 0.90, "m", sp(t, "0,90 mètre")), leaf("clear_width", "ge", 0.83, "m", sp(t, "0,83 mètre")), span=sp(t, "une largeur minimale de 0,90 mètre et une largeur minimale de passage libre lorsque le vantail est ouvert à 90°, de 0,83 mètre")),
        span=sp(t, t))],
        [({"doors": [{"door_kind": "entree", "width": 0.95, "clear_width": 0.85}]}, [SAT]), ({"doors": [{"door_kind": "entree", "width": 0.95, "clear_width": 0.80}]}, [VIO]),
         ({"doors": [{"door_kind": "interieure", "width": 0.5, "clear_width": 0.5}]}, [SAT])]))

    t = "- Si la pente du plan incliné est supérieure à 4%, une main courante sera installée sur un côté au moins. Cette dernière présentera les caractéristiques illustrées dans le croquis ci-contre."
    out.append(case("caue7", fr, "item 7", t, "fr", [N("slope", "%"), N("handrail_sides", "1")], [Obligation(
        id="o1", applicability=leaf("slope", "gt", 4, "%", sp(t, "Si la pente du plan incliné est supérieure à 4%")), requirement=leaf("handrail_sides", "ge", 1, "1", sp(t, "une main courante sera installée sur un côté au moins")),
        span=sp(t, "Si la pente du plan incliné est supérieure à 4%, une main courante sera installée sur un côté au moins"))],
        [({"slope": 5, "handrail_sides": 1}, [SAT]), ({"slope": 5, "handrail_sides": 0}, [VIO]), ({"slope": 4, "handrail_sides": 0}, [NA]), ({"slope": 3, "handrail_sides": 0}, [NA])]))

    t = "- Lorsque la place est située en extérieur, elle doit se raccorder sans ressaut de plus de 2cm de haut au cheminement d’accès au logement. A partir de la place, ce passage doit être horizontal sur au moins 1,40 mètre de long."
    out.append(case("caue16", fr, "item 16", t, "fr", [B("place_exterieure"), N("step_height", "m"), N("horizontal_length", "m")], [
        Obligation(id="o1", applicability=leaf("place_exterieure", "eq", True, span=sp(t, "Lorsque la place est située en extérieur")), requirement=leaf("step_height", "le", 2, "cm", sp(t, "sans ressaut de plus de 2cm de haut")),
                   span=sp(t, "Lorsque la place est située en extérieur, elle doit se raccorder sans ressaut de plus de 2cm de haut au cheminement d’accès au logement")),
        Obligation(id="o2", requirement=leaf("horizontal_length", "ge", 1.40, "m", sp(t, "au moins 1,40 mètre de long")), span=sp(t, "A partir de la place, ce passage doit être horizontal sur au moins 1,40 mètre de long"))],
        [({"place_exterieure": True, "step_height": 0.02, "horizontal_length": 1.5}, [SAT, SAT]), ({"place_exterieure": True, "step_height": 0.03, "horizontal_length": 1.0}, [VIO, VIO]),
         ({"place_exterieure": False, "step_height": 0.05, "horizontal_length": 1.5}, [NA, SAT])]))

    t = "- si un ressaut ne peut être évité, il sera de 2cm de haut maximum et aura un bord arrondi ou chanfreiné."
    out.append(case("caue30", fr, "item 30", t, "fr", [B("ressaut_inevitable"), N("step_height", "m"), B("bord_arrondi"), B("bord_chanfreine")], [Obligation(
        id="o1", applicability=leaf("ressaut_inevitable", "eq", True, span=sp(t, "si un ressaut ne peut être évité")),
        requirement=all_of(leaf("step_height", "le", 2, "cm", sp(t, "2cm de haut maximum")), any_of(leaf("bord_arrondi", "eq", True, span=sp(t, "arrondi")), leaf("bord_chanfreine", "eq", True, span=sp(t, "chanfreiné")), span=sp(t, "un bord arrondi ou chanfreiné")),
                           span=sp(t, "il sera de 2cm de haut maximum et aura un bord arrondi ou chanfreiné")), span=sp(t, t))],
        [({"ressaut_inevitable": True, "step_height": 0.02, "bord_arrondi": True, "bord_chanfreine": False}, [SAT]), ({"ressaut_inevitable": True, "step_height": 0.02, "bord_arrondi": False, "bord_chanfreine": False}, [VIO]),
         ({"ressaut_inevitable": True, "step_height": 0.03, "bord_arrondi": True, "bord_chanfreine": True}, [VIO]), ({"ressaut_inevitable": False, "step_height": 0.1, "bord_arrondi": False, "bord_chanfreine": False}, [NA]),
         ({"ressaut_inevitable": True, "step_height": 0.01, "bord_arrondi": False, "bord_chanfreine": True}, [SAT])]))

    t = "-Lorsqu’il est situé entre des parois pleines, l’escalier doit comporter au moins une main courante répondant aux caractéristiques données dans le paragraphe 2 cheminement extérieur du présent document."
    out.append(case("caue_p25", fr, "P25", t, "fr", [B("entre_parois_pleines"), N("main_courante_count", "1")], [Obligation(
        id="o1", applicability=leaf("entre_parois_pleines", "eq", True, span=sp(t, "Lorsqu’il est situé entre des parois pleines")), requirement=leaf("main_courante_count", "ge", 1, "1", sp(t, "au moins une main courante")),
        span=sp(t, "Lorsqu’il est situé entre des parois pleines, l’escalier doit comporter au moins une main courante"))],
        [({"entre_parois_pleines": True, "main_courante_count": 1}, [SAT]), ({"entre_parois_pleines": True, "main_courante_count": 0}, [VIO]), ({"entre_parois_pleines": False, "main_courante_count": 0}, [NA])]))

    t = "\u2013 un accès aux balcons, loggias et/ou terrasses, obligatoire depuis une pièce de vie lorsque ceux-ci présentent une profondeur suffisante (0,60 m),"
    out.append(case("aqc6", aqc, "item 6", t, "fr", [N("balcony_depth", "m"), B("acces_depuis_piece_de_vie")], [Obligation(
        id="o1", applicability=leaf("balcony_depth", "ge", 0.60, "m", sp(t, "profondeur suffisante (0,60 m)")), requirement=leaf("acces_depuis_piece_de_vie", "eq", True, span=sp(t, "obligatoire depuis une pièce de vie")),
        span=sp(t, "un accès aux balcons, loggias et/ou terrasses, obligatoire depuis une pièce de vie lorsque ceux-ci présentent une profondeur suffisante (0,60 m)"))],
        [({"balcony_depth": 0.6, "acces_depuis_piece_de_vie": True}, [SAT]), ({"balcony_depth": 0.7, "acces_depuis_piece_de_vie": False}, [VIO]),
         ({"balcony_depth": 0.5, "acces_depuis_piece_de_vie": False}, [NA]), ({"balcony_depth": 0.59, "acces_depuis_piece_de_vie": False}, [NA])],
        note="'profondeur suffisante (0,60 m)' is read as depth of at least 0.60 m"))
    return out


def rule_cases() -> list[dict]:
    """The 10 rule_now items of benchmarks/checklist_labels.json, as trees read from the sentence. `program` is the expression the
    benchmark wrote (None when it declined). `index` is the obligation of the tree that corresponds to it."""
    rt = ["bedroom", "kitchen", "living", "office", "corridor", "bathroom"]
    al, be, bl, sp_ = "us_allentown_irc_checklist.md", "us_berkeley_floor_plan_checklist.pdf", "us_bloomfield_residential_checklist.pdf", "us_stpete_residential_checklist.pdf"
    out = []

    t = "Habitable rooms must have 8% window area to floor area ratio. 303.1"
    out.append(case("item 6", al, "item 6", t, "en", [S("room_type", rt, own="member", coll="rooms"), N("window_area_ratio", "1", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$r", where=any_of(*[leaf("room_type", "eq", v, span=sp(t, "Habitable rooms")) for v in ("bedroom", "kitchen", "living", "office")], span=sp(t, "Habitable rooms")), span=sp(t, "Habitable rooms")),
        requirement=leaf("window_area_ratio", "ge", 8, "%", sp(t, "8% window area to floor area ratio")), span=sp(t, "Habitable rooms must have 8% window area to floor area ratio"))], [], "equal"))
    out[-1]["index"] = 0
    t = "Habitable rooms must be min. 70 s.f. except kitchens, also min. 7' in any dimension. 304.1, 304.2"
    hab = lambda: any_of(*[leaf("room_type", "eq", v, span=sp(t, "Habitable rooms")) for v in ("bedroom", "kitchen", "living", "office")], span=sp(t, "Habitable rooms"))  # noqa: E731
    out.append(case("item 9", al, "item 9", t, "en", [S("room_type", rt, own="member", coll="rooms"), N("area_m2", "m2", own="member", coll="rooms"), N("min_width_m", "m", own="member", coll="rooms")], [
        Obligation(id="o1", scope=Scope(collection="rooms", variable="$r", where=hab()), requirement=leaf("area_m2", "ge", 70, "ft2", sp(t, "min. 70 s.f.")),
                   exceptions=[Exc(when=leaf("room_type", "eq", "kitchen", span=sp(t, "kitchens")), cue="except", span=sp(t, "except kitchens"))], span=sp(t, "Habitable rooms must be min. 70 s.f. except kitchens")),
        Obligation(id="o2", scope=Scope(collection="rooms", variable="$r", where=hab()), requirement=leaf("min_width_m", "ge", 7, "ft", sp(t, "min. 7' in any dimension")), span=sp(t, "also min. 7' in any dimension"))], [],
        "area and width together in the benchmark rule"))
    out[-1]["index"] = None                     # the benchmark wrote one program for both obligations: compared separately below
    t = "1 egress door required min. 32\". Door must not require a key to open from inside. 311.2"
    out.append(case("item 14", al, "item 14", t, "en", [B("is_egress", own="member", coll="doors"), N("width_m", "m", own="member", coll="doors"), B("requires_key_inside", own="member", coll="doors")], [
        Obligation(id="o1", scope=Scope(quantifier="exists", collection="doors", variable="$d", where=leaf("is_egress", "eq", True, span=sp(t, "egress door")), span=sp(t, "1 egress door")),
                   requirement=leaf("width_m", "ge", 32, "in", sp(t, "min. 32\"")), span=sp(t, "1 egress door required min. 32\"")),
        Obligation(id="o2", modality="prohibition", scope=Scope(collection="doors", variable="$d", where=leaf("is_egress", "eq", True, span=sp(t, "Door")), span=sp(t, "Door")),
                   requirement=leaf("requires_key_inside", "eq", True, span=sp(t, "require a key to open from inside")), span=sp(t, "Door must not require a key to open from inside"))], [], "benchmark declined"))
    out[-1]["index"] = None
    t = "Hallways must be min. 3' wide. 311.6"
    out.append(case("item 15", al, "item 15", t, "en", [S("room_type", rt, own="member", coll="rooms"), N("min_width_m", "m", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$r", where=leaf("room_type", "eq", "corridor", span=sp(t, "Hallways")), span=sp(t, "Hallways")),
        requirement=leaf("min_width_m", "ge", 3, "ft", sp(t, "min. 3' wide")), span=sp(t, "Hallways must be min. 3' wide"))], []))
    out[-1]["index"] = 0
    t = "Dimension and label all rooms (existing and proposed) including basement spaces (e.g. bedrooms, kitchen, etc.)"
    out.append(case("item 2b", be, "item 2", t, "en", [B("has_label", own="member", coll="rooms"), B("is_dimensioned")], [
        Obligation(id="o1", scope=Scope(collection="rooms", variable="$a", span=sp(t, "all rooms")), requirement=leaf("has_label", "eq", True, span=sp(t, "label")), span=sp(t, "label all rooms")),
        Obligation(id="o2", requirement=leaf("is_dimensioned", "eq", True, span=sp(t, "Dimension")), span=sp(t, "Dimension"))], [], "benchmark rule is partial: label only"))
    out[-1]["index"] = 0
    t = "All permit applications for residential projects shall include a scaled and dimensioned floor plan representing existing and proposed work."
    out.append(case("P1", be, "P1", t, "en", [B("is_dimensioned"), B("scale_stated")], [Obligation(
        id="o1", requirement=all_of(leaf("scale_stated", "eq", True, span=sp(t, "scaled")), leaf("is_dimensioned", "eq", True, span=sp(t, "dimensioned")), span=sp(t, "scaled and dimensioned")), span=sp(t, t))], []))
    out[-1]["index"] = 0
    t = "All drawings shall be completely dimensioned"
    out.append(case("item 2", bl, "item 2", t, "en", [B("is_dimensioned")], [Obligation(id="o1", requirement=leaf("is_dimensioned", "eq", True, span=sp(t, "completely dimensioned")), span=sp(t, t))], []))
    out[-1]["index"] = 0
    t = "Intended use of each room or space"
    out.append(case("item 21", bl, "item 21", t, "en", [B("has_label", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$a", span=sp(t, "each room or space")), requirement=leaf("has_label", "eq", True, span=sp(t, "Intended use")), span=sp(t, t))], [], "benchmark declined"))
    out[-1]["index"] = None
    t = "Site Plan (FBC-B 107.2.5) \u2013 Plans must be to scale and show the scale utilized"
    out.append(case("item 25", sp_, "item 25", t, "en", [B("scale_stated")], [Obligation(id="o1", requirement=leaf("scale_stated", "eq", True, span=sp(t, "show the scale utilized")), span=sp(t, "Plans must be to scale and show the scale utilized"))], []))
    out[-1]["index"] = 0
    t = "Size and arrangement of all rooms/spaces labeled with intended use"
    out.append(case("item 48", sp_, "item 48", t, "en", [B("has_label", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$a", span=sp(t, "all rooms/spaces")), requirement=leaf("has_label", "eq", True, span=sp(t, "labeled with intended use")), span=sp(t, t))], []))
    out[-1]["index"] = 0
    return out


def relation_cases() -> list[dict]:
    """Relation sentences (the examples of xeval/relation_arm.py). The relation is a yes/no fact of the room: no link or route node yet."""
    out = []
    t = "No door or opening connects a garage directly to a bedroom."
    out.append(case("rel1", "relation_arm", "doc", t, "en", [S("room_type", ["garage", "bedroom", "kitchen"], own="member", coll="rooms"), B("joined_to_bedroom", own="member", coll="rooms")], [Obligation(
        id="o1", modality="prohibition", scope=Scope(collection="rooms", variable="$r", where=leaf("room_type", "eq", "garage", span=sp(t, "a garage")), span=sp(t, "a garage")),
        requirement=leaf("joined_to_bedroom", "eq", True, span=sp(t, "door or opening connects a garage directly to a bedroom")), span=sp(t, t))],
        [({"rooms": [{"room_type": "garage", "joined_to_bedroom": False}]}, [SAT]), ({"rooms": [{"room_type": "garage", "joined_to_bedroom": True}]}, [VIO]), ({"rooms": [{"room_type": "kitchen", "joined_to_bedroom": True}]}, [SAT])]))
    t = "Every habitable room reaches an exit without passing through a bathroom."
    out.append(case("rel2", "relation_arm", "doc", t, "en", [B("habitable", own="member", coll="rooms"), B("reaches_exit_avoiding_bathroom", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$r", where=leaf("habitable", "eq", True, span=sp(t, "habitable room")), span=sp(t, "Every habitable room")),
        requirement=leaf("reaches_exit_avoiding_bathroom", "eq", True, span=sp(t, "reaches an exit without passing through a bathroom")), span=sp(t, t))],
        [({"rooms": [{"habitable": True, "reaches_exit_avoiding_bathroom": True}]}, [SAT]), ({"rooms": [{"habitable": True, "reaches_exit_avoiding_bathroom": False}]}, [VIO]), ({"rooms": [{"habitable": False, "reaches_exit_avoiding_bathroom": False}]}, [SAT])]))
    t = "Every enclosed room has at least one door."
    out.append(case("rel3", "relation_arm", "doc", t, "en", [B("enclosed", own="member", coll="rooms"), N("door_count", "1", own="member", coll="rooms")], [Obligation(
        id="o1", scope=Scope(collection="rooms", variable="$r", where=leaf("enclosed", "eq", True, span=sp(t, "enclosed room")), span=sp(t, "Every enclosed room")),
        requirement=leaf("door_count", "ge", 1, "1", sp(t, "at least one door")), span=sp(t, t))],
        [({"rooms": [{"enclosed": True, "door_count": 1}]}, [SAT]), ({"rooms": [{"enclosed": True, "door_count": 0}]}, [VIO]), ({"rooms": [{"enclosed": False, "door_count": 0}]}, [SAT])]))
    return out



def rounded(tree: NormTree) -> NormTree:
    """The same tree with every limit written in the unit of its fact, rounded to 5 decimals (what the benchmark rule does)."""
    from reviewpulse.interpreter import units

    t = tree.model_copy(deep=True)
    for ob in t.obligations:
        from reviewpulse.normative.schema import cond_paths

        for _, c in cond_paths(ob):
            if c.kind == "test" and t.fact(c.fact).kind == "number" and c.unit not in ("1", t.fact(c.fact).unit):
                c.value = round(units.convert(float(c.value), c.unit, t.fact(c.fact).unit), 5)
                c.unit = t.fact(c.fact).unit
    return t

# --------------------------------------------------------------------------------------------------------- perturbations
FLIP = {"ge": "le", "le": "ge", "gt": "lt", "lt": "gt", "eq": "ne", "ne": "eq"}
OTHER_UNIT = {"m": "cm", "cm": "m", "mm": "m", "in": "ft", "ft": "in", "m2": "cm2", "ft2": "m2", "min": "h", "%": "1"}


def mutations(tree: NormTree) -> list[dict]:
    """Every single node perturbation: {obligation index, kind, path (in the obligation), arg}."""
    out = []
    for i, ob in enumerate(tree.obligations):
        d = ob.model_dump()
        cond_roots = [("requirement", d["requirement"]), ("applicability", d["applicability"]), ("scope.where", (d["scope"] or {}).get("where"))]
        cond_roots += [(f"exceptions[{k}].when", e["when"]) for k, e in enumerate(d["exceptions"])]

        def walk(path, c, i=i):
            if c is None:
                return
            if c["kind"] == "test":
                spec = tree.fact(c["fact"])
                if spec.kind == "number":
                    out.append({"i": i, "kind": "swapped_direction", "path": path})
                    if c["unit"] in OTHER_UNIT:
                        out.append({"i": i, "kind": "wrong_unit", "path": path})
                    out.append({"i": i, "kind": "wrong_number", "path": path})
                elif spec.kind == "boolean":
                    out.append({"i": i, "kind": "swapped_polarity", "path": path})
                else:
                    out.append({"i": i, "kind": "swapped_polarity", "path": path})
            else:
                if c["kind"] == "any" and path.startswith("requirement"):
                    out.append({"i": i, "kind": "dropped_alternative", "path": path})
                if c["kind"] in ("any", "all"):
                    out.append({"i": i, "kind": "or_and_swap", "path": path})
                    if len(c["args"]) >= 2 and not path.startswith("requirement") and not path.startswith("exceptions"):
                        out.append({"i": i, "kind": "dropped_condition", "path": path + ".args[0]"})
            for k, a in enumerate(c["args"]):
                walk(f"{path}.args[{k}]", a, i)

        for p, c in cond_roots:
            walk(p, c, i)
        if d["applicability"] is not None:
            out.append({"i": i, "kind": "dropped_condition", "path": "applicability"})
        if d["scope"] and d["scope"]["where"] is not None:
            out.append({"i": i, "kind": "dropped_condition", "path": "scope.where"})
        for k in range(len(d["exceptions"])):
            out.append({"i": i, "kind": "dropped_exception", "path": f"exceptions[{k}]"})
        out.append({"i": i, "kind": "swapped_modality", "path": "modality"})
        if d["scope"]:
            out.append({"i": i, "kind": "swapped_quantifier", "path": "scope.quantifier"})
    return out


def mutate(tree: NormTree, m: dict) -> NormTree:
    ob = tree.obligations[m["i"]].model_dump()
    toks = _tokens(m["path"])
    kind = m["kind"]
    if kind in ("swapped_direction", "wrong_unit", "wrong_number", "swapped_polarity"):
        node, _ = _get(ob, toks)
        if kind == "swapped_direction":
            node["op"] = FLIP[node["op"]]
        elif kind == "wrong_unit":
            node["unit"] = OTHER_UNIT[node["unit"]]
        elif kind == "wrong_number":
            node["value"] = node["value"] * 1.1 if node["value"] else 1
        else:
            if type(node["value"]) is bool:
                node["value"] = not node["value"]
            else:
                node["op"] = FLIP[node["op"]]
    elif kind == "dropped_alternative":
        node, _ = _get(ob, toks)
        node["args"] = node["args"][:-1]
        if len(node["args"]) == 1:
            _set(ob, toks, node["args"][0])
    elif kind == "or_and_swap":
        node, _ = _get(ob, toks)
        node["kind"] = "any" if node["kind"] == "all" else "all"
    elif kind == "dropped_condition":
        if m["path"] in ("applicability", "scope.where"):
            _set(ob, toks, None)
        else:
            parent, _ = _get(ob, toks[:-2])
            parent["args"] = parent["args"][1:]
            if len(parent["args"]) == 1 and False:
                pass
    elif kind == "dropped_exception":
        ob["exceptions"].pop(toks[1])
    elif kind == "swapped_modality":
        ob["modality"] = "prohibition" if ob["modality"] == "obligation" else "obligation"
    elif kind == "swapped_quantifier":
        ob["scope"]["quantifier"] = "exists" if ob["scope"]["quantifier"] == "forall" else "forall"
    obs = [o.model_copy(deep=True) for o in tree.obligations]
    obs[m["i"]] = Obligation.model_validate(ob)
    return tree.model_copy(update={"obligations": obs}, deep=True)


class MutantParser:
    """A faulty reader: reads the words exactly, then makes one mistake of the planted kind."""

    def __init__(self, m: dict):
        self.m = m

    def parse(self, words, facts, language, tree):
        return mutate(TemplateParser().parse(words, facts, language, tree), self.m)


def related(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".") or a.startswith(b + "[") or b.startswith(a + "[")


def hit(repair: list[str], i: int, path: str) -> bool:
    slot = path.split(".")[0].split("[")[0]
    for r in repair:
        idx, _, p = r.partition(":")
        if idx != str(i):
            continue
        if related(p, path) or p == slot or (slot == "exceptions" and p.startswith("exceptions")):
            return True
    return False


# ------------------------------------------------------------------------------------------------------------------- cue arm
def span_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def cue_arm_report(cases) -> dict:
    rep = {"sentences": len(cases), "with_exception": 0, "exception_found": 0, "with_condition": 0, "condition_found": 0,
           "exception_seed_total": 0, "exception_seed_true": 0, "condition_seed_total": 0, "condition_seed_true": 0, "misses": []}
    for c in cases:
        tree = build(c)
        seeds = cue_seeds(c["text"])
        exc_spans = [(e.span.start, e.span.end) for ob in tree.obligations for e in ob.exceptions if e.span]
        cond_spans = [(ob.applicability.span.start, ob.applicability.span.end) for ob in tree.obligations if ob.applicability is not None and ob.applicability.span]
        es = [s for s in seeds if s.role == "exception"]
        cs = [s for s in seeds if s.role == "condition"]
        if exc_spans:
            rep["with_exception"] += 1
            ok = any(span_overlap(s.span, x) for s in es for x in exc_spans)
            rep["exception_found"] += ok
            if not ok:
                rep["misses"].append((c["id"], "exception not found"))
        if cond_spans:
            rep["with_condition"] += 1
            ok = any(span_overlap(s.span, x) for s in cs for x in cond_spans)
            rep["condition_found"] += ok
            if not ok:
                rep["misses"].append((c["id"], "condition not found"))
        rep["exception_seed_total"] += len(es)
        rep["exception_seed_true"] += sum(any(span_overlap(s.span, x) for x in exc_spans) for s in es)
        rep["condition_seed_total"] += len(cs)
        rep["condition_seed_true"] += sum(any(span_overlap(s.span, x) for x in cond_spans) for s in cs)
    return rep


# ------------------------------------------------------------------------------------------------------------- oracle client
class OracleClient:
    """A scripted client that answers from the hand tree (no model): it shows the drafter plumbing end to end."""

    def __init__(self, tree: NormTree):
        self.tests = [(n, tree.fact(n.fact)) for ob in tree.obligations for _, n in __import__("reviewpulse.normative.schema", fromlist=["cond_paths"]).cond_paths(ob) if n.kind == "test"]
        self.tree = tree

    def _gold(self, q: str):
        for n, spec in self.tests:
            quote = self.tree.quote(n.span)
            if spec.kind == "number":
                m = re.search(r"number '([^']*)'|value '([^']*)'", q)
                num = (m.group(1) or m.group(2)) if m else None
                if num and num in quote:
                    return n, spec
            else:
                part = q.split("?", 1)[-1].strip()
                if quote and quote in part or part and part in quote:
                    return n, spec
        return None, None

    def complete(self, system, user, schema):
        d = json.loads(user)
        q, opts = d["question"], list(d["options"])
        n, spec = self._gold(q)
        if n is None:
            return {"choice": "none"}
        if q.startswith("Which fact does the number"):
            return {"choice": n.fact}
        if q.startswith("In which direction"):
            return {"choice": n.op}
        if q.startswith("Which yes/no fact"):
            return {"choice": n.fact}
        if q.startswith("Does the clause require"):
            return {"choice": "forbid" if self.tree.obligations[0].modality == "prohibition" else "require"}
        if q.startswith("Does the clause say"):
            return {"choice": "holds" if n.value is True else "not_holds"}
        return {"choice": opts[0]}


def drafter_report(cases) -> dict:
    rep = {"tried": 0, "drafted": 0, "equivalent": 0, "rows": []}
    for c in cases:
        tree = build(c)
        if len(tree.obligations) != 1 or tree.obligations[0].scope is not None or tree.language != "en":
            continue
        ob = tree.obligations[0]
        if any(spec.kind == "string" for spec in tree.facts):
            continue
        rep["tried"] += 1
        d = Drafter(OracleClient(tree), tree.facts, tree.language)
        got = d.draft(c["text"], tree.clause_id, c["doc"])
        row = {"id": c["id"], "drafted": got is not None}
        if got is not None:
            rep["drafted"] += 1
            eq = equivalent(tree, got, n_worlds=64)
            row.update({"equivalent": eq.equivalent, "unresolved": got.obligations[0].unresolved, "repair": eq.repair})
            rep["equivalent"] += eq.equivalent
        rep["rows"].append(row)
        _ = ob
    return rep


# --------------------------------------------------------------------------------------------------------------- the audit
def clause_text(doc: str) -> str:
    name = doc.rsplit(".", 1)[0] if doc.endswith((".md", ".pdf")) else doc
    path = next((ROOT / "reports" / "m14_split_cache2" / name).glob("*.json"), None)
    if path is None:
        return ""
    return re.sub(r"\s+", " ", " ".join(c["text"] for c in json.loads(path.read_text(encoding="utf-8"))["clauses"]))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/m21_normative")
    ap.add_argument("--worlds", type=int, default=128)
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res: dict = {}

    # ---- 1. the 30 real sentences
    cases = sentences()
    docs = {}
    rows, bad = [], []
    for c in cases:
        row = {"id": c["id"], "doc": c["doc"], "lang": c["lang"], "obligations": len(c["obs"]), "exceptions": 0, "conditions": 0}
        try:
            tree = build(c)
            row["valid"] = True
            row["ungrounded"] = tree.ungrounded()
            row["in_document"] = norm(c["text"])[:60] in docs.setdefault(c["doc"], norm(clause_text(c["doc"])))
            row["exceptions"] = sum(len(o.exceptions) for o in tree.obligations)
            row["conditions"] = sum(o.applicability is not None or bool(o.scope and o.scope.where) for o in tree.obligations)
            compile_tree(tree)
            row["compiles"] = True
            fails = []
            for k, (world, expect) in enumerate(c["checks"]):
                members = world if "rooms" in world or "doors" in world or "basements" in world else None
                got = run_tree(tree, None if members else world, members)
                if got != expect:
                    fails.append({"world": k, "expected": expect, "got": got})
            row["worlds_checked"] = len(c["checks"])
            row["world_failures"] = fails
            rts = {}
            for lang in ("en", "fr", "de"):
                r = roundtrip(tree, lang=lang, n_worlds=args.worlds)
                rts[lang] = r.ok
                if not r.ok:
                    row.setdefault("roundtrip_errors", []).append((lang, r.error))
            row["roundtrip"] = rts
        except Exception as exc:  # noqa: BLE001
            row.update({"valid": False, "error": f"{type(exc).__name__}: {exc}"})
            bad.append(row)
        rows.append(row)
    res["sentences"] = rows
    n = len(rows)
    res["sentence_summary"] = {
        "n": n, "valid": sum(r.get("valid", False) for r in rows), "ungrounded_nodes": sum(len(r.get("ungrounded", [])) for r in rows),
        "found_in_document": sum(r.get("in_document", False) for r in rows), "compile_ok": sum(r.get("compiles", False) for r in rows),
        "hand_worlds": sum(r.get("worlds_checked", 0) for r in rows), "hand_world_failures": sum(len(r.get("world_failures", [])) for r in rows),
        "roundtrip_ok": {lang: sum(r.get("roundtrip", {}).get(lang, False) for r in rows) for lang in ("en", "fr", "de")},
        "with_exception": sum(1 for r in rows if r["exceptions"]), "with_condition": sum(1 for r in rows if r["conditions"]),
        "multi_obligation": sum(1 for r in rows if r["obligations"] > 1),
    }

    # ---- 2. planted perturbations, through the equivalence and through the faulty reader
    kinds: dict[str, Counter] = defaultdict(Counter)
    survivors, rt_missed, nolocal = [], [], []
    loc = Counter()
    for c in cases:
        tree = build(c)
        for m in mutations(tree):
            try:
                mt = mutate(tree, m)
            except (ValueError, KeyError, TypeError):
                kinds[m["kind"]]["invalid"] += 1               # the perturbation does not even validate: counted apart
                continue
            eq = equivalent(tree, mt, n_worlds=args.worlds)
            k = kinds[m["kind"]]
            k["total"] += 1
            k["rejected"] += not eq.equivalent
            if eq.equivalent:
                survivors.append({"id": c["id"], **m})
            r = roundtrip(tree, MutantParser(m), lang=tree.language, n_worlds=args.worlds)
            k["roundtrip_rejected"] += not r.ok
            if r.ok:
                rt_missed.append({"id": c["id"], **m})
            else:
                loc["total"] += 1
                good = hit(r.repair, m["i"], m["path"])
                loc["named"] += good
                if not good:
                    nolocal.append({"id": c["id"], **m, "repair": r.repair})
    res["planted"] = {k: dict(v) for k, v in sorted(kinds.items())}
    tot = sum(v["total"] for v in kinds.values())
    rej = sum(v["rejected"] for v in kinds.values())
    res["planted_total"] = {"perturbations": tot, "rejected": rej, "rate": rej / tot if tot else None,
                            "roundtrip_rejected": sum(v["roundtrip_rejected"] for v in kinds.values()),
                            "localised": dict(loc), "survivors": survivors, "roundtrip_missed": rt_missed, "not_localised": nolocal[:30]}

    # ---- 3. the labelled rule_now rules
    rows3 = json.loads((ROOT / "reports" / "benchmark_final" / "rows.jsonl").read_text(encoding="utf-8").splitlines()[0]) and \
        [json.loads(line) for line in (ROOT / "reports" / "benchmark_final" / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = json.loads((ROOT / "benchmarks" / "checklist_labels.json").read_text(encoding="utf-8"))
    by = {(r["doc"], r["id"]): r for r in rows3}
    rrows = []
    for c in rule_cases():
        tree = build(c)
        compile_tree(tree)
        lab = labels[c["doc"]][c["clause"]]
        r = by.get((c["doc"], c["clause"]))
        rule = r.get("readback") if r else None
        row = {"doc": c["doc"][:14], "item": c["clause"], "label": lab["label"], "benchmark_outcome": r["outcome"] if r else None, "benchmark_rule": rule,
               "tree_ungrounded": tree.ungrounded(), "tree_roundtrip": roundtrip(tree, lang="en", n_worlds=args.worlds).ok, "compare": None, "compare_rounded": None}
        if rule:
            cat = {f.name: Binding(kind=f.kind, unit=f.unit) for f in tree.facts}
            prog = Program.model_validate(compile_expr_program({"id": "bm", "title": "benchmark", "require": rule, "sources": [{"clause": "x", "quote": "q"}]}, "d", cat, {"building"}))
            if c.get("index") is None:                  # one benchmark program for several obligations: compare with all of them together
                eq = compare_program_all(tree, prog, n_worlds=args.worlds)
                row["compare"] = {"equivalent": eq.equivalent, "worlds": eq.n_worlds, "exact": eq.exact, "reason": eq.reason, "mismatch": eq.mismatches[:1]}
                eq = compare_program_all(rounded(tree), prog, n_worlds=args.worlds)
                row["compare_rounded"] = {"equivalent": eq.equivalent, "worlds": eq.n_worlds, "exact": eq.exact, "reason": eq.reason, "mismatch": eq.mismatches[:1]}
            else:
                for name, t2 in (("compare", tree), ("compare_rounded", rounded(tree))):
                    eq = compare_program(t2, c["index"], prog, n_worlds=args.worlds)
                    row[name] = {"equivalent": eq.equivalent, "worlds": eq.n_worlds, "exact": eq.exact, "reason": eq.reason, "mismatch": eq.mismatches[:1]}
        rrows.append(row)
    res["rules"] = rrows

    # ---- 4. relations
    rel = []
    for c in relation_cases():
        tree = build(c)
        compile_tree(tree)
        fails = []
        for k, (world, expect) in enumerate(c["checks"]):
            got = run_tree(tree, None, world)
            if got != expect:
                fails.append({"world": k, "expected": expect, "got": got})
        rel.append({"id": c["id"], "world_failures": fails, "roundtrip": roundtrip(tree, lang="en", n_worlds=args.worlds).ok, "ungrounded": tree.ungrounded()})
    res["relations"] = rel
    rel_tot = tot_mut = rej_mut = 0
    for c in relation_cases():
        tree = build(c)
        for m in mutations(tree):
            try:
                mt = mutate(tree, m)
            except (ValueError, KeyError, TypeError):
                continue
            tot_mut += 1
            rej_mut += not equivalent(tree, mt, n_worlds=args.worlds).equivalent
    res["relations_planted"] = {"perturbations": tot_mut, "rejected": rej_mut}
    del rel_tot

    # ---- 5. the cue arm, the drafter
    res["cue_arm"] = cue_arm_report(cases)
    res["drafter_oracle"] = drafter_report(cases)
    res["smt"] = __import__("reviewpulse.normative", fromlist=["smt"]).smt()
    res["seconds"] = round(time.time() - t0, 1)
    (out / "summary.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    s = res["sentence_summary"]
    print(f"sentences {s['n']}: valid {s['valid']}, found in document {s['found_in_document']}, ungrounded nodes {s['ungrounded_nodes']}, compile {s['compile_ok']}")
    print(f"  hand worlds {s['hand_worlds']}: failures {s['hand_world_failures']}; round trip ok {s['roundtrip_ok']}")
    print(f"  with exception {s['with_exception']}, with condition {s['with_condition']}, several obligations {s['multi_obligation']}")
    print(f"planted: {rej}/{tot} rejected by equivalence ({rej / tot:.4f}); by the faulty reader {res['planted_total']['roundtrip_rejected']}/{tot}; "
          f"node named {loc['named']}/{loc['total']}")
    for k, v in res["planted"].items():
        print(f"  {k:22s} {v.get('rejected', 0)}/{v.get('total', 0)} rejected, reader {v.get('roundtrip_rejected', 0)}, not valid {v.get('invalid', 0)}")
    print(f"  survivors: {len(survivors)}")
    for sv in survivors:
        print("   ", sv)
    for r in rrows:
        print("rule", r["doc"], r["item"], r["label"], r["benchmark_outcome"], "compare:", r["compare"], "rounded:", r.get("compare_rounded"), "rt", r["tree_roundtrip"], "ungrounded", r["tree_ungrounded"])
    for r in rel:
        print("relation", r)
    print("relations planted", res["relations_planted"])
    print("cue arm", {k: v for k, v in res["cue_arm"].items() if k != "misses"}, res["cue_arm"]["misses"])
    d = res["drafter_oracle"]
    print("drafter (oracle client)", {k: d[k] for k in ("tried", "drafted", "equivalent")})
    for r in d["rows"]:
        print("   ", r)
    print("smt", res["smt"], "seconds", res["seconds"])
    for r in rows:
        if r.get("world_failures") or not r.get("valid") or r.get("ungrounded") or not r.get("in_document", True) or r.get("roundtrip_errors"):
            print("PROBLEM", {k: r[k] for k in r if k in ("id", "error", "ungrounded", "in_document", "world_failures", "roundtrip_errors")})


if __name__ == "__main__":
    main()
