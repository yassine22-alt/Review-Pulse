"""I4 - LLM drafting and validation.

An LLM turns one clause into a *draft* rule by choosing from the controlled
vocabulary and the function registry; the validator rejects anything outside
them; a curator approves (I5). The LLM never judges a drawing and no drawing is
ever sent - only clause text.

Determinism: current Claude models reject sampling parameters, so instead of
"temperature 0" we fix the prompt, constrain the output with a JSON schema, and
store model id, date and prompt hash with every draft.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from .clauses import Clause, split_document
from .schema import Rule, vocab

DEFAULT_MODEL = "claude-opus-5-5"


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, json_schema: dict) -> dict: ...


class OllamaClient:
    """Local open-source model served by Ollama (default; free, offline, nothing leaves the machine).

    Ollama constrains decoding with the JSON schema (``format``) and, unlike hosted frontier models,
    accepts temperature 0 and a fixed seed, so drafts are reproducible.
    Install: https://ollama.com, then ``ollama pull qwen2.5:7b``."""

    def __init__(self, model: str = "qwen2.5:7b", host: str | None = None, seed: int = 42,
                 timeout_s: float = 600.0, num_ctx: int = 8192):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.seed, self.timeout_s, self.num_ctx = seed, timeout_s, num_ctx

    def _post(self, path: str, body: dict) -> dict:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.host + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama not reachable at {self.host} ({e}); start it with `ollama serve`") from e

    def available(self) -> bool:
        try:
            tags = self._post_get("/api/tags")
        except RuntimeError:
            return False
        return any(m.get("name", "").split(":")[0] == self.model.split(":")[0] for m in tags.get("models", []))

    def _post_get(self, path: str) -> dict:
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(self.host + path, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(str(e)) from e

    def complete(self, system: str, user: str, json_schema: dict) -> dict:
        out = self._post("/api/chat", {
            "model": self.model, "stream": False, "format": json_schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "seed": self.seed, "num_ctx": self.num_ctx},
        })
        return json.loads(out["message"]["content"])


def make_client(backend: str = "ollama", model: str | None = None) -> LLMClient:
    if backend == "ollama":
        return OllamaClient(model=model or "qwen2.5:7b")
    if backend == "claude":
        return ClaudeClient(model=model or DEFAULT_MODEL)
    raise ValueError(f"unknown LLM backend {backend!r} (ollama | claude)")


class ClaudeClient:
    """Anthropic SDK client (``pip install -e ".[llm]"``; credentials from the environment)."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "medium"):
        import anthropic

        self.model = model
        self.effort = effort
        self.client = anthropic.Anthropic()

    def complete(self, system: str, user: str, json_schema: dict) -> dict:
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": json_schema}},
            # if a safety classifier declines, the API re-runs the request on a fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"model declined: {getattr(resp.stop_details, 'category', None)}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("draft truncated at max_tokens")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)


class ReplayClient:
    """Returns stored answers (tests, offline demos). ``answers`` maps clause id -> output dict."""

    def __init__(self, answers: dict[str, dict], model: str = "replay"):
        self.answers = answers
        self.model = model

    def complete(self, system: str, user: str, json_schema: dict) -> dict:
        cid = json.loads(user.split("CLAUSE_JSON:", 1)[1])["id"]
        return self.answers[cid]


# ---------------------------------------------------------------------------
# Frame: the LLM answers small, plain questions; code builds the rule.
# (a 7B model is reliable at "what is measured, compared how, to which number"; it is not reliable
# at assembling a full rule object, so that part is deterministic)

HABITABLE = ["bedroom", "living", "dining", "kitchen", "office"]

# property -> (function, class, family, subject kind, params). Subject kind: room | door | window | none
PROPERTIES: dict[str, tuple] = {
    "clear_width": ("width_m", "threshold", "C", "element", {}),
    "room_minimum_dimension": ("min_width_m", "threshold", "C", "room", {}),
    "corridor_width": ("min_width_m", "threshold", "C", "room", {}),
    "floor_area": ("area_m2", "threshold", "C", "room", {}),
    "glazed_area_ratio": ("ratio", "derived", "C", "room", {}),
    "travel_distance_to_exit": ("shortest_path_m", "traversal", "C", "room", {}),
    "number_of_exits": ("count_exits", "count", "C", "none", {}),
    "route_to_exit": ("exists_path", "traversal", "C", "room", {}),
    "forbidden_direct_connection": ("forbidden_link", "traversal", "C", "none", {}),
    "single_door_room_has_window": ("dead_end_no_window", "traversal", "C", "room", {}),
    "rooms_labelled": ("present", "presence", "P", "none", {"what": "room_labels"}),
    "dimensions_present": ("present", "presence", "P", "none", {"what": "dimensions"}),
    "title_block_complete": ("present", "presence", "P", "none", {"what": "title_block"}),
    "dimension_chain_sum": ("sum_parts", "arithmetic", "K", "none", {}),
    "written_vs_drawn_dimension": ("drawn_vs_stated", "arithmetic", "K", "none", {}),
    "stated_vs_drawn_area": ("stated_vs_computed_area", "arithmetic", "K", "none", {}),
    "tags_match_schedule": ("join", "cross_reference", "K", "none", {"mode": "widths"}),
    "schedule_completeness": ("join", "presence", "P", "none", {"mode": "completeness"}),
    "door_swing_overlap": ("swing_conflicts", "derived", "Q", "element", {"max_verdict": "WARNING"}),
}
# measurable in principle, but not from a floor plan alone (sections, schedules with heights, specs)
NEEDS_OTHER_DATA = ["door_height", "window_sill_height", "ceiling_height", "stair_riser_or_going"]
NOT_CHECKABLE = ["fire_resistance", "acoustic_performance", "thermal_performance", "materials_or_workmanship",
                 "other"]
COMPARISONS = {"at_least": ">=", "at_most": "<=", "more_than": ">", "less_than": "<", "equal_to": "==",
               "no_number": None}
UNITS = ["m", "cm", "mm", "m2", "percent", "fraction", "count", "none"]
FN_UNIT = {"width_m": "m", "min_width_m": "m", "area_m2": "m2", "shortest_path_m": "m", "ratio": "ratio",
           "count_exits": "count"}


def output_schema() -> dict:
    V = vocab()
    rooms = {"type": "array", "items": {"type": "string", "enum": V["room_types"]}}
    str_list = {"type": "array", "items": {"type": "string"}}
    props = sorted(PROPERTIES) + NEEDS_OTHER_DATA + NOT_CHECKABLE
    return {"type": "object", "additionalProperties": False, "properties": {
        "property": {"type": "string", "enum": props,
                     "description": "what the clause measures or requires"},
        "subject": {"type": "string", "enum": ["room", "door", "window", "dwelling", "drawing", "schedule"]},
        "room_types": rooms,
        "avoid_room_types": rooms,
        "forbidden_pairs": {"type": "array", "items": rooms},
        "comparison": {"type": "string", "enum": list(COMPARISONS)},
        "number": {"type": ["number", "null"], "description": "the threshold exactly as written (decimal point)"},
        "unit_written": {"type": "string", "enum": UNITS},
        "severity": {"type": "string", "enum": V["severities"]},
        "title": {"type": "string"},
        "rase": {"type": "object", "additionalProperties": False,
                 "properties": {k: str_list for k in ("requirement", "applicability", "selection", "exception")},
                 "required": ["requirement", "applicability", "selection", "exception"]},
    }, "required": ["property", "subject", "room_types", "avoid_room_types", "forbidden_pairs", "comparison",
                    "number", "unit_written", "severity", "title", "rase"]}


SYSTEM = """You read one clause of a building regulation and answer questions about it as JSON.
- property: what the clause measures or requires (pick the closest; use one of fire_resistance,
  acoustic_performance, thermal_performance, materials_or_workmanship, other when no floor-plan property fits;
  heights and sills are door_height / window_sill_height / ceiling_height).
- subject: what the requirement applies to.
- room_types: which rooms it applies to. "habitable room" / "piece principale" / "piece de vie" means
  bedroom, living, dining, kitchen, office. Leave empty when it applies to doors, windows or the whole dwelling.
- avoid_room_types: for route_to_exit only, rooms the route must not pass through.
- forbidden_pairs: for forbidden_direct_connection only, each pair of room types that must not be connected.
- comparison: at_least for "at least / au moins / minimum / not less than / pas inferieur";
  at_most for "at most / au plus / maximum / not exceed / ne depasse pas"; no_number when no threshold.
- number and unit_written: the threshold exactly as written (0,80 m -> 0.8 m; 850 mm -> 850 mm;
  10% -> 10 percent; one sixth -> 0.1667 fraction; two exits -> 2 count).
- rase: quote the clause words for requirement, applicability, selection, exception (empty lists if absent).
Never invent a number that is not in the clause."""

EXAMPLES = """Examples:
"Hallways shall be no narrower than 1.10 m." -> property corridor_width, subject room, room_types [corridor],
  comparison at_least, number 1.1, unit_written m
"La surface de la salle de bain est d'au moins 4 m2." -> property floor_area, subject room,
  room_types [bathroom], comparison at_least, number 4, unit_written m2
"Les portes palieres ont une largeur minimale de 90 cm." -> property clear_width, subject door,
  comparison at_least, number 90, unit_written cm
"Kitchens shall not open directly onto a bathroom." -> property forbidden_direct_connection, subject room,
  forbidden_pairs [[kitchen, bathroom]], comparison no_number, number null, unit_written none
"Every bedroom must reach the entrance without passing through the garage." -> property route_to_exit,
  subject room, room_types [bedroom], avoid_room_types [garage], comparison no_number
"Le parcours vers la sortie la plus proche est limite a 20 m." -> property travel_distance_to_exit,
  subject room, room_types [bedroom, living, dining, kitchen, office], comparison at_most, number 20, unit_written m
"Walls between flats shall be rated EI 60." -> property fire_resistance, comparison no_number, number null
"Each plan shows the scale, the date and the revision." -> property title_block_complete, subject drawing"""


def build_prompt(clause: Clause) -> tuple[str, str]:
    user = EXAMPLES + "\n\nCLAUSE_JSON:" + json.dumps({"id": clause.id, "text": clause.text}, ensure_ascii=False)
    return SYSTEM, user


def prompt_hash() -> str:
    s, u = build_prompt(Clause(id="x", heading="", text="", page=0, start=0, end=0))
    return hashlib.sha256((s + u + json.dumps(output_schema(), sort_keys=True)).encode()).hexdigest()[:12]


# deterministic cross-check of the comparison words (French and English, accents stripped)
_AT_LEAST = re.compile(r"\b(au moins|au minimum|minimum|minimale?s?|pas inferieure?s? a|n.est pas inferieure?|"
                       r"at least|not less than|no less than|no narrower than|minimum of)\b|>=|≥")
_AT_MOST = re.compile(r"\b(au plus|au maximum|maximum|maximale?s?|ne depasse pas|ne doit pas depasser|limitee? a|"
                      r"pas superieure?s? a|at most|not exceed|shall not exceed|no more than|maximum of)\b|<=|≤")


# wordings where one comparison and one number do not capture the clause: flagged for the curator
# (measured on CODE-ACCORD: ranges and permissions were the unflagged wrong directions)
_RANGE = re.compile(r"\d\s*(?:-|–|to|a|et|and)\s*\d+(?:[.,]\d+)?\s*(?:mm|cm|m\b|m2|%|percent|per cent|degrees)|"
                    r"\bbetween\s+\d|\bentre\s+\d")
_PERMISSION = re.compile(r"\b(may|can|is permitted to|are permitted to|is allowed to|peut|peuvent|est autorisee?s?|"
                         r"sont autorisee?s?)\b(?:\s+\w+){0,3}\s+(?:be\s+)?(?:more|less|greater|smaller|exceed|"
                         r"higher|lower|wider|narrower|depasser|superieure?s?|inferieure?s?|plus)\b")


def wording_flags(text: str) -> list[str]:
    from .clauses import _strip_accents

    t = _strip_accents(text.lower())
    out = []
    if _RANGE.search(t) or (_AT_LEAST.search(t) and _AT_MOST.search(t)):
        out.append("the clause states a range (two limits): one comparison cannot express it")
    if _PERMISSION.search(t):
        out.append("the clause grants a permission, not a requirement: check the direction of the limit")
    return out


def comparison_from_text(text: str) -> str | None:
    from .clauses import _strip_accents

    t = _strip_accents(text.lower())
    lo, hi = bool(_AT_LEAST.search(t)), bool(_AT_MOST.search(t))
    if lo != hi:
        return "at_least" if lo else "at_most"
    return None


def _numbers_in(text: str) -> list[float]:
    return [float(m.replace(",", ".")) for m in re.findall(r"\d+(?:[.,]\d+)?", text)]


def to_rule_dict(out: dict, clause: Clause, doc: str) -> dict | None:
    prop = out.get("property")
    if prop not in PROPERTIES:
        return None
    fn, cls, family, kind, params = PROPERTIES[prop]
    check: dict[str, Any] = {"fn": fn}
    comp = comparison_from_text(clause.text) or out.get("comparison")
    op = COMPARISONS.get(comp)
    num, unit = out.get("number"), out.get("unit_written", "none")
    if fn in FN_UNIT and op and num is not None:
        val = float(num)
        if unit == "cm":
            val /= 100
        elif unit == "mm":
            val /= 1000
        elif unit == "percent":
            val /= 100
        check.update(op=op, value=round(val, 4), unit=FN_UNIT[fn])
    applies: dict[str, Any] = {}
    rooms = out.get("room_types") or []
    if kind == "room":
        applies["room_type"] = rooms or HABITABLE
    elif kind == "element":
        applies["element"] = "window" if out.get("subject") == "window" else "door"
    if fn in ("exists_path", "shortest_path_m"):
        check.update({"from": "$room", "to": "EXIT", "via_edges": ["door", "opening"]})
        if fn == "exists_path" and out.get("avoid_room_types"):
            check["avoid"] = {"room_type": out["avoid_room_types"]}
    if fn == "forbidden_link":
        check["pairs"] = [p for p in out.get("forbidden_pairs", []) if len(p) == 2]
        check["via_edges"] = ["door", "opening"]
    safe = re.sub(r"-+", "-", "".join(ch if ch.isalnum() else "-" for ch in clause.id)).strip("-")
    messages = {"threshold": "{detected}; {required} required.", "traversal": "{room.label}: {detected}.",
                "count": "{detected} found; {required} required."}
    return {"id": f"D-{safe}", "title": out.get("title") or prop.replace("_", " "), "family": family,
            "class": cls, "applies_to": applies, "check": check, "severity": out.get("severity", "major"),
            "needs": [], "source": {"doc": doc, "clause": clause.id, "span": [clause.start, clause.end]},
            "message": messages.get(cls, "{detected}"), "params": dict(params), "status": "draft", "version": 1}


def checkable_of(out: dict) -> str:
    prop = out.get("property")
    if prop in PROPERTIES:
        return "from_drawings"
    if prop in NEEDS_OTHER_DATA:
        return "needs_other_data"
    return "not_checkable"


# ---------------------------------------------------------------------------
# Validation

@dataclass
class Draft:
    clause_id: str
    clause_text: str
    span: list[int]
    checkable: str
    rase: dict
    rationale: str
    rule: dict | None
    errors: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    model: str = ""
    date: str = ""
    prompt_hash: str = ""


def plausibility(rule: dict) -> list[str]:
    """Flag values outside plausible ranges (vocab.yaml); flagged drafts still go to the curator."""
    P = vocab().get("plausible", {})
    c = rule["check"]
    v = c.get("value")
    if v is None:
        return []
    fn, at = c["fn"], rule.get("applies_to", {})
    key = None
    if fn == "width_m" and at.get("element") == "door":
        key = "door.width_m"
    elif fn == "min_width_m" and "corridor" in at.get("room_type", []):
        key = "corridor.min_width_m"
    elif fn == "area_m2":
        key = "room.area_m2"
    elif fn == "min_width_m":
        key = "room.min_width_m"
    if key and key in P:
        lo, hi = P[key]
        if not (lo <= v <= hi):
            return [f"value {v} outside plausible range {lo}-{hi} for {key}"]
    return []


def _spelled_out(num: float, text: str) -> bool:
    """A number written as a word ("at least one exit") is in the text; the wording tables know the common languages."""
    from ..xeval.verify import detect_language, number_words

    return any(abs(num - x) < 1e-6 for x in number_words(text, detect_language(text)))


def validate(out: dict, clause: Clause, doc: str) -> Draft:
    d = Draft(clause_id=clause.id, clause_text=clause.text, span=[clause.start, clause.end],
              checkable=checkable_of(out), rase=out.get("rase", {}),
              rationale=f"property {out.get('property')}, comparison {out.get('comparison')}, "
                        f"number {out.get('number')} {out.get('unit_written')}", rule=None)
    d.flags += wording_flags(clause.text)
    if d.checkable != "from_drawings":
        return d
    rd = to_rule_dict(out, clause, doc)
    if rd is None:
        d.errors.append("no function for this property")
        return d
    num = out.get("number")
    if num is not None and out.get("unit_written") != "fraction"             and not any(abs(num - x) < 1e-6 for x in _numbers_in(clause.text))             and not _spelled_out(num, clause.text):
        d.flags.append(f"number {num} does not appear in the clause text")
    try:
        rule = Rule.model_validate(rd)
        d.rule = yaml.safe_load(_dump(rule))
        d.flags += plausibility(rd)
        from .review import threshold_gaps

        gaps = threshold_gaps(rule)
        if gaps:
            d.errors.append(f"threshold rule without {gaps}: the clause states no limit to compare with")
    except Exception as e:  # noqa: BLE001 - kept with the reason, never silently dropped
        d.rule = rd
        msg = " ".join(ln.strip() for ln in str(e).splitlines() if ln.strip() and "errors.pydantic.dev" not in ln)
        d.errors.append(msg[:500])
    return d


def _dump(rule: Rule) -> str:
    from .schema import dump_rule

    return dump_rule(rule)


def draft_document(doc_path: str | Path, client: LLMClient, out_dir: str | Path = "drafts",
                   only: list[str] | None = None, progress=None) -> Path:
    """``progress(done, total)`` is called after each clause (a job runner reports it)."""
    doc_path = Path(doc_path)
    full, clauses = split_document(doc_path)
    schema = output_schema()
    ph = prompt_hash()
    today = dt.date.today().isoformat()
    drafts = []
    todo = [cl for cl in clauses if not (only and cl.id not in only)
            and not (cl.kind == "table_row" and not any(ch.isdigit() for ch in cl.text))]
    for k, cl in enumerate(todo):
        if progress:
            progress(k, len(todo))
        system, user = build_prompt(cl)
        try:
            out = client.complete(system, user, schema)
            d = validate(out, cl, str(doc_path).replace(os.sep, "/"))
        except Exception as e:  # noqa: BLE001 - one failing clause must not stop the document
            d = Draft(clause_id=cl.id, clause_text=cl.text, span=[cl.start, cl.end], checkable="error", rase={},
                      rationale="", rule=None, errors=[f"LLM call failed: {e}"])
        d.model, d.date, d.prompt_hash = client.model, today, ph
        drafts.append(d)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{doc_path.stem}.drafts.yaml"
    out.write_text(yaml.safe_dump([d.__dict__ for d in drafts], sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    return out


def load_drafts(path: str | Path) -> list[Draft]:
    return [Draft(**d) for d in yaml.safe_load(Path(path).read_text(encoding="utf-8"))]
