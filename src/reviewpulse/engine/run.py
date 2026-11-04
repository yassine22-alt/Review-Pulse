"""J1 - Engine: run approved rules over a BuildingModel; every finding carries its proof.

Plain deterministic Python; nothing here calls an LLM.

Evidence format (sheet space):
    {"polylines": [[(x, y), ...]], "polygons": [[(x, y), ...]],
     "points": [(x, y)], "labels": [{"at": (x, y), "text": "..."}]}
"""

from __future__ import annotations

import string

from ..rules.registry import resolve
from ..rules.schema import Rule
from ..schema import BuildingModel, Finding
from .context import Context
from .policy import Decision, Raw, decide


class _SafeDict(dict):
    def __missing__(self, key):
        return "?"


class _Obj:
    """Attribute access for message templates: {room.label}, {subject.tag}."""

    def __init__(self, d: dict):
        self._d = d

    def __getattr__(self, k):
        v = self._d.get(k)
        return "?" if v is None else v

    def __format__(self, spec):
        return format(str(self._d.get("__str__", "?")), spec)


def render_message(template: str, raw: Raw, detected: str | None, required: str | None) -> str:
    values = _SafeDict(detected=detected or "?", required=required or "?")
    for k, v in raw.vars.items():
        values[k] = _Obj(v) if isinstance(v, dict) else v
    try:
        return string.Formatter().vformat(template, (), values)
    except (KeyError, AttributeError, IndexError, ValueError):
        return template


def not_evaluated(rule: Rule, missing: list[str], tier: str) -> Finding:
    return Finding(rule_id=rule.id, verdict="NOT_EVALUATED", severity=rule.severity, subject_ids=[],
                   message=f"{rule.title}: not evaluated, missing {', '.join(missing)}", tier=tier,
                   source=rule.source.model_dump(), evidence={"missing": missing})


OCR_ABSENCE = "verify on the drawing (text read by OCR may be missed)"
OCR_GROUP_MIN = 4


def _group_ocr_absences(rule: Rule, fs: list[Finding], tier: str) -> list[Finding]:
    """Absences read from OCR'd text are uncertain one by one: many of them (an unread tag on every
    door) become one WARNING listing every subject, instead of a page of identical warnings."""
    if len(fs) < OCR_GROUP_MIN:
        return fs
    subjects = [i for f in fs for i in f.subject_ids]
    polys = [p for f in fs for p in f.evidence.get("polygons", [])]
    return [Finding(rule_id=rule.id, verdict="WARNING", severity=rule.severity, subject_ids=subjects,
                    message=f"{rule.title}: {len(fs)} items without the required text as read by OCR "
                            f"[{OCR_ABSENCE}]",
                    tier=tier, source=rule.source.model_dump(),
                    evidence={"grouped": len(fs), **({"polygons": polys} if polys else {})})]


def run(model: BuildingModel, rules: list[Rule], confirmed: set | None = None,
        include_drafts: bool = False) -> list[Finding]:
    ctx = Context.of(model, confirmed)
    out: list[Finding] = []
    scale_verified = model.sheet.scale.method in ("dxf_units", "dimension_consensus", "user", "scale_bar")
    # text read by OCR can be missed: an absence (no label, no tag) found on it is never certain
    ocr_text = any(t.prov.source == "ocr" for t in model.sheet.texts) or model.sheet.mode == "raster"
    for rule in rules:
        if rule.status != "approved" and not (include_drafts and rule.status == "draft"):
            continue
        missing = [n for n in rule.needs if not ctx.has(n)]
        if missing:
            out.append(not_evaluated(rule, missing, ctx.tier))
            continue
        fn = resolve(rule.check.fn)
        raws: list[Raw] = fn(rule, ctx)
        ocr_absences: list[Finding] = []
        for raw in raws:
            # a check that names no deciding elements is decided by its subjects: below T1 they must be
            # confirmed too, or an absence read from estimated input (a missed OCR label) could FAIL
            all_conf = all(ctx.is_confirmed(i) for i in (raw.deciding_ids or raw.subject_ids))
            dec = decide(raw, ctx.tier, guidance=rule.is_guidance,
                         max_verdict=rule.params.get("max_verdict", "FAIL"),
                         all_confirmed=all_conf, scale_verified=scale_verified)
            if dec.verdict == "FAIL" and any((r := ctx.room(i)) is not None
                                             and r.prov.evidence.get("label_source") in ("llm", "vlm")
                                             for i in raw.subject_ids):
                # the room's type was read by a language or vision model, not matched in the lexicon
                dec = Decision("WARNING", "verify room type (label read by a language model)")
            elif dec.verdict in ("FAIL", "WARNING") and rule.cls == "presence" and ocr_text:
                # an absence (no label, no tag) found in OCR'd text is uncertain first of all because
                # the text may simply not have been read
                dec = Decision("WARNING", OCR_ABSENCE)
            msg = render_message(rule.message, raw, raw.detected, raw.required)
            if dec.reason and dec.verdict != "PASS":
                msg += f" [{dec.reason}]"
            ev = dict(raw.evidence)
            if raw.note:
                ev["note"] = raw.note
            if raw.deciding_ids:
                ev["deciding_ids"] = raw.deciding_ids
            f = Finding(rule_id=rule.id, verdict=dec.verdict, severity=rule.severity,
                        subject_ids=raw.subject_ids, message=msg, detected=raw.detected,
                        required=raw.required, tier=ctx.tier, evidence=ev, source=rule.source.model_dump())
            (ocr_absences if dec.reason == OCR_ABSENCE else out).append(f)
        out += _group_ocr_absences(rule, ocr_absences, ctx.tier)
        if rule.applies_to.get("room_type"):
            # a room whose type is unknown (no label read) may be one this rule applies to: say so,
            # rather than let the rule pass by never looking at it
            untyped = [r.id for r in model.rooms if r.type is None and not r.is_corridor]
            if untyped:
                out.append(Finding(rule_id=rule.id, verdict="NOT_EVALUATED", severity=rule.severity,
                                   subject_ids=untyped, tier=ctx.tier, source=rule.source.model_dump(),
                                   message=f"{rule.title}: not evaluated for {len(untyped)} room(s) of unknown "
                                           "type (no label read); label or confirm their type",
                                   evidence={"missing": ["room_type"]}))
    return out


def summarise(findings: list[Finding]) -> dict:
    s: dict[str, int] = {}
    for f in findings:
        s[f.verdict] = s.get(f.verdict, 0) + 1
    return s
