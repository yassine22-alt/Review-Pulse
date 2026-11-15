"""What kind of sheet is this? A floor plan, or an elevation, a section, a site plan, a schedule, a cover page?

Real drawing sets mix all of these, and the wall finder happily "finds" rooms in the studs of an elevation (measured on a real
22 sheet set: 58 and 114 rooms on two elevation sheets). A reviewer would be misled by findings built on that, so only a sheet
that shows a floor plan is read as one; every other sheet is named, and said not to be a floor plan.

How it is decided, in this order:
  1. a vision model looks at the whole sheet and names it (any language, any drawing style: nothing is read from the text).
     The answer is cached by image, so a sheet is judged once.
  2. when no vision model is reachable: the words of the title block and large text (several languages), then geometry
     (a floor plan has a connected wall network enclosing rooms).
Both are a recommendation the reviewer can see (`sheet.kind_source`), not a hidden decision.

REVIEWPULSE_SHEET_KIND = auto (default) | vlm | text | off
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path

MODEL = "qwen2.5vl:7b"
CACHE = Path(os.environ.get("REVIEWPULSE_CACHE", Path.home() / ".cache" / "reviewpulse")) / "sheet_kind"

KINDS = ["floor_plan", "elevation", "section_or_detail", "site_plan", "structural_plan", "ceiling_or_services_plan",
         "schedule_or_notes", "cover_or_3d", "sketch", "other"]
# the sheet types the rest of the product knows
SHEET_TYPE = {"floor_plan": "floor_plan", "elevation": "elevation", "section_or_detail": "section", "site_plan": "site",
              "structural_plan": "structural", "ceiling_or_services_plan": "ceiling", "schedule_or_notes": "schedule",
              "cover_or_3d": "cover", "sketch": "other", "other": "other"}

PROMPT = """This is one sheet of an architectural or engineering drawing set. Say what the sheet mainly shows.

kind, exactly one of:
- floor_plan: a plan view of a level of a building, seen from above, with walls, doors and rooms (also the plan of an
  apartment or a single room layout)
- elevation: a side view of the outside of a building (facade), or a wall seen from the side
- section_or_detail: a cut through a building or construction details at larger scale
- site_plan: the plot, boundaries, streets, the building footprint on the land
- structural_plan: foundation, framing or roof structure plans
- ceiling_or_services_plan: reflected ceiling, electrical, plumbing or other services plans
- schedule_or_notes: tables, schedules, general notes, legends, indexes
- cover_or_3d: a title page, renderings or 3D views
- sketch: a hand drawn sketch
- other

contains_floor_plan: true if a floor plan (as defined above) appears anywhere on the sheet, even next to other drawings.
Reply with JSON only."""

SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": KINDS}, "contains_floor_plan": {"type": "boolean"}},
          "required": ["kind", "contains_floor_plan"]}

# fallback: the words of the title block, several languages; first match wins, floor plans last
WORDS = [
    ("elevation", r"elevation|facade|fa[cç]ade|alzado|ansicht|prospetto|gevel|\bvues?\b"),
    ("section_or_detail", r"\bsections?\b|\bcoupes?\b|\bcorte\b|schnitt|sezione|doorsnede|\bdetails?\b|d[eé]tail"),
    ("schedule_or_notes", r"tableau|nomenclature|schedule|\bnotes?\b|legend|index|sommaire|menuiseries|liste"),
    ("structural_plan", r"coffrage|ferraillage|fondations?|foundation|structural|framing|charpente|roof plan|toiture"),
    ("ceiling_or_services_plan", r"ceiling|plafond|reflected|electrical|plumbing|[eé]lectricit|plomberie"),
    ("site_plan", r"plan de masse|situation|site plan|site (?:&|and) |cadastre|lageplan|planimetria"),
    ("cover_or_3d", r"\bcover\b|title sheet|summary|page de garde|render|perspective|3d"),
    ("floor_plan", r"\bplan\b|rez.de.chaussee|\brdc\b|etage|niveau|floor plan|ground floor|grundriss|planta|pianta|plattegrond"),
]


def mode() -> str:
    return os.environ.get("REVIEWPULSE_SHEET_KIND", "auto").lower()


def vlm_available(host: str | None = None) -> bool:
    import urllib.request

    host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
            return any(m.get("name", "").startswith(MODEL.split(":")[0]) for m in json.loads(r.read()).get("models", []))
    except Exception:  # noqa: BLE001 - no server, no model: the text and geometry fallback applies
        return False


def _png_for_model(png_path: Path, long_side: int = 1024) -> bytes:
    from PIL import Image

    im = Image.open(png_path).convert("RGB")
    k = long_side / max(im.size)
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def ask_vlm(png_path: Path, host: str | None = None, model: str = MODEL, timeout_s: float = 300.0) -> dict | None:
    """{"kind", "contains_floor_plan"} from the vision model, or None when it cannot answer."""
    import urllib.request

    png = _png_for_model(png_path)
    key = hashlib.sha256(png + model.encode() + PROMPT.encode()).hexdigest()[:24]
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    body = {"model": model, "stream": False, "format": SCHEMA,
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(png).decode()]}],
            "options": {"temperature": 0, "seed": 42, "num_predict": 60}}
    req = urllib.request.Request(host + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            out = json.loads(json.loads(r.read())["message"]["content"])
    except Exception:  # noqa: BLE001
        return None
    if out.get("kind") not in KINDS or not isinstance(out.get("contains_floor_plan"), bool):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out), encoding="utf-8")
    return out


def from_words(blob: str) -> str | None:
    from .text_classify import normalise

    t = normalise(blob)
    for kind, pat in WORDS:
        if re.search(pat, t):
            return kind
    return None


def judge(png_path: Path | None, title_words: str, n_walls: int, n_rooms: int) -> dict:
    """{"kind", "contains_floor_plan", "source"} for one sheet."""
    m = mode()
    if m == "off":
        return {"kind": "floor_plan", "contains_floor_plan": True, "source": "off"}
    if m in ("auto", "vlm") and png_path is not None and png_path.exists() and (m == "vlm" or vlm_available()):
        out = ask_vlm(png_path)
        if out is not None:
            return {**out, "source": "vision"}
    kind = from_words(title_words)
    if kind is None:
        kind = "floor_plan" if n_walls >= 4 and n_rooms >= 1 else "other"
    return {"kind": kind, "contains_floor_plan": kind == "floor_plan", "source": "text"}


def plan_bearing(j: dict) -> bool:
    """Only a sheet whose MAIN content is a floor plan is read as one. The vision model's extra "a floor plan appears somewhere
    on the sheet" flag is not used: measured on real pages it wrongly admitted 4 of 17 other sheets (see scripts/sheet_kind_eval.py)."""
    return j["kind"] == "floor_plan"
