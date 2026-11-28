"""Label-value pairs from the text layer of a page.

A label is a short run of words whose words are all a field's cue (plus qualifiers, or a level word for an area). Its
value is read from the same line (after a colon or just after the label), from the line to its right on the same row, or
from the line below it (a header above its value or its column of values). Ruled or not makes no difference: only the
text and its places are used, never the lines of the drawing.

The labeler is a parameter, so the embedding arm can recognise a label the words do not, and everything after it
(layout, value reading, source) is shared.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..drawingset.pagedata import Line, PageData
from ..drawingset.views import read_level
from ..drawingset.vocab import Vocab, fold, load_vocab
from .spec import Field, Spec, find_run, load_spec, tokens
from .values import Parsed, parse_value, vocab_match

BBox = tuple[float, float, float, float]
SPLIT = re.compile(r"^(?P<lab>[^:=]{1,70}?)\s*[:=]\s*(?P<val>.*)$")
MAX_LABEL_WORDS = 9


@dataclass
class LabelHit:
    field: str
    lang: str
    level: str | None = None
    unit: str | None = None
    via: str = "words"                 # words or embedding
    score: float = 1.0                 # how sure the labeler is (1 for an exact word match)


@dataclass
class Hit:
    field: str
    entity: str
    parsed: Parsed
    page: int
    layout: str
    label: str
    value_text: str
    region: BBox
    lang: str
    via: str = "words"
    label_score: float = 1.0
    extra: dict = field(default_factory=dict)


Labeler = Callable[[str], "LabelHit | None"]


def box(*lines: Line) -> BBox:
    return (min(ln.x0 for ln in lines), min(ln.y0 for ln in lines), max(ln.x1 for ln in lines), max(ln.y1 for ln in lines))


def _strip_units(label: str, spec: Spec) -> tuple[tuple[str, ...], str | None]:
    """The words of a label without a unit written in brackets or last (AREA (SF), LIVABLE SF, Wohnflaeche in m2)."""
    unit = None
    for inner in re.findall(r"[\(\[]([^\)\]]*)[\)\]]", label):
        t = tokens(inner)
        for n in (3, 2, 1):
            if t[:n] in spec.unit_words and len(t) == n:
                unit = spec.unit_words[t[:n]]
    base = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", label)
    w = tokens(base)
    if len(w) > 1:
        for n in (3, 2, 1):
            if w[-n:] in spec.unit_words and len(w) > n:
                unit = unit or spec.unit_words[w[-n:]]
                w = w[:-n]
                break
        if len(w) > 2 and w[-1] == "in":
            w = w[:-1]
    return w, unit


def make_word_labeler(spec: Spec, vocab: Vocab) -> Labeler:
    cache: dict[str, LabelHit | None] = {}

    def label(text: str) -> LabelHit | None:
        key = text
        if key in cache:
            return cache[key]
        w, unit = _strip_units(text, spec)
        hit = None
        if w and len(w) <= MAX_LABEL_WORDS:
            best = None                                    # (rest words, -cue length, field, lang, level)
            for f in spec.fields.values():
                for lang, cue in f.cues:
                    i = find_run(w, cue)
                    if i < 0:
                        continue
                    rest = w[:i] + w[i + len(cue):]
                    level = None
                    if rest and all(r in spec.qualifiers for r in rest):
                        pass
                    elif rest and f.by_level and (lv := read_level(" ".join(rest), vocab)) is not None:
                        level = lv[0]
                    elif rest:
                        continue
                    k = (len(rest), -len(cue))
                    if best is None or k < best[0]:
                        best = (k, f.name, lang, level)
            if best:
                hit = LabelHit(best[1], best[2], best[3], unit)
        cache[key] = hit
        return hit

    return label


def _is_label(text: str, labeler: Labeler) -> bool:
    t = text.strip().rstrip(":=").strip()
    return bool(t) and len(t.split()) <= MAX_LABEL_WORDS and labeler(t) is not None


def _usable(r: Line, labeler: Labeler, f: Field, spec: Spec, lang: str, unit: str | None) -> bool:
    """A neighbour line can be the value unless it is the label of another pair. A line that opens with a colon is a value,
    and so is one that reads as a value of this field even if its words could also be a label ("NEW CONSTRUCTION")."""
    if not _is_label(r.text, labeler) or r.text.lstrip().startswith((":", "=")):
        return True
    return parse_value(f, r.text, spec, lang, unit).status != "reject"


def _right(ln: Line, pg: PageData, labeler: Labeler, f: Field, spec: Spec, lang: str, unit: str | None) -> Line | None:
    h = ln.h
    best = None
    for r in pg.lines:
        if r is ln or not r.horizontal:
            continue
        if abs(r.cy - ln.cy) > 0.7 * max(h, r.h) or r.x0 < ln.x1 - 0.5 * h or r.x0 - ln.x1 > 60 * h:
            continue
        if not _usable(r, labeler, f, spec, lang, unit):
            continue
        if best is None or r.x0 < best.x0:
            best = r
    return best


def _below(ln: Line, pg: PageData, labeler: Labeler, f: Field, spec: Spec, lang: str, unit: str | None,
           maxgap: float = 2.5) -> Line | None:
    h = ln.h
    best = None
    for r in pg.lines:
        if r is ln or not r.horizontal or r.y0 < ln.y1 - 0.3 * h or r.y0 - ln.y1 > maxgap * h:
            continue
        left = abs(r.x0 - ln.x0) <= 3 * h
        centred = abs(r.cx - ln.cx) <= 3 * h
        right = abs(r.x1 - ln.x1) <= 3 * h
        if not (left or centred or right) or not _usable(r, labeler, f, spec, lang, unit):
            continue
        if best is None or r.y0 < best.y0:
            best = r
    return best


def _column(header: Line, pg: PageData, labeler: Labeler, f: Field, spec: Spec, lang: str, unit: str | None, vocab: Vocab
            ) -> list[tuple[str, Parsed, Line, Line | None]]:
    """The values under a header, one per row, each with the line to its left on the same row (the row's label)."""
    h = header.h
    rows, last = [], header
    cands = sorted((r for r in pg.lines if r is not header and r.horizontal and r.y0 >= header.y1 - 0.3 * h), key=lambda r: r.y0)
    for r in cands:
        if r.y0 - last.y1 > 3 * h:
            break
        if not (abs(r.x0 - header.x0) <= 4 * h or abs(r.cx - header.cx) <= 4 * h or abs(r.x1 - header.x1) <= 4 * h):
            continue
        p = parse_value(f, r.text, spec, lang, unit)
        if p.status == "reject" or p.status == "unstated" and "no unit" not in p.note:
            if _is_label(r.text, labeler):
                break
            continue
        left = [c for c in pg.lines if c is not r and c.horizontal and abs(c.cy - r.cy) <= 0.7 * max(h, r.h) and c.x1 <= r.x0 + h]
        lab = max(left, key=lambda c: c.x1) if left else None
        rows.append((lab.text.strip() if lab else "", p, r, lab))
        last = r
    return rows


def read_page(pg: PageData, spec: Spec | None = None, vocab: Vocab | None = None, labeler: Labeler | None = None) -> list[Hit]:
    spec = spec or load_spec()
    vocab = vocab or load_vocab()
    labeler = labeler or make_word_labeler(spec, vocab)
    hits: list[Hit] = []
    used: set[int] = set()

    def emit(f: Field, lh: LabelHit, p: Parsed, layout: str, ln: Line, label: str, vtext: str, vline: Line | None,
             level: str | None = None):
        ent = f"level:{level}" if level else "building"
        hits.append(Hit(f.name, ent, p, pg.index, layout, label, vtext, box(ln, vline) if vline else box(ln), lh.lang, lh.via,
                        lh.score))

    for ln in pg.lines:
        if not ln.horizontal or id(ln) in used:
            continue
        text = ln.text.strip()
        if len(text) > 160:
            continue
        # 1. label and value in one line: "SPRINKLERS: NO", "Wohnflaeche ca. 61,3 m2", "LIVABLE SF:    4,586"
        m = SPLIT.match(text)
        tries: list[tuple[str, str, str]] = []
        if m and m.group("val").strip():
            tries.append((m.group("lab"), m.group("val"), "same line"))
        words = text.split()
        whole = len(words) <= MAX_LABEL_WORDS and labeler(text.rstrip(":=").strip()) is not None
        if len(words) <= MAX_LABEL_WORDS + 6 and not whole:
            for k in range(len(words) - 1, 0, -1):
                tries.append((" ".join(words[:k]), " ".join(words[k:]), "inline"))
        done = False
        for lab, val, layout in tries:
            lh = labeler(lab.strip())
            if lh is None:
                continue
            f = spec.fields[lh.field]
            if layout == "inline" and f.free and not f.value_patterns:      # free text needs a colon, a cell or a header
                continue
            p = parse_value(f, val, spec, lh.lang, lh.unit)
            if p.status == "reject" or layout == "inline" and not p.canonical:
                continue
            emit(f, lh, p, layout, ln, lab.strip(), val.strip(), None, lh.level)
            done = True
            break
        if done:
            continue
        # statements of a whole line: "FULLY SPRINKLERED"
        if len(words) <= 6:
            for f in spec.fields.values():
                if f.kind == "bool" and (f.true_phrases or f.false_phrases):
                    p = parse_value(f, text, spec)
                    if p.status == "value" and p.note == "stated phrase":
                        emit(f, LabelHit(f.name, "en"), p, "statement", ln, "", text, None)
                        hits[-1].extra["statement"] = True
                        done = True
                        break
        if done:
            continue
        # 2. label alone: the value is to its right or below
        label = text.rstrip(":=").strip()
        if text.endswith(".") and not text.rstrip(".").endswith(":"):      # the end of a sentence, not a label
            continue
        lh = labeler(label) if label and len(label.split()) <= MAX_LABEL_WORDS else None
        if lh is None:
            continue
        f = spec.fields[lh.field]
        r = _right(ln, pg, labeler, f, spec, lh.lang, lh.unit)
        if r is not None:
            p = parse_value(f, r.text, spec, lh.lang, lh.unit)
            if p.status != "reject":
                emit(f, lh, p, "right", ln, label, r.text.strip().lstrip(":=").strip(), r, lh.level)
                used.add(id(r))
                continue
        if f.by_level and f.kind == "number":
            rows = _column(ln, pg, labeler, f, spec, lh.lang, lh.unit, vocab)
            good = []
            for rl, p, vl, _lab in rows:
                lv = read_level(rl, vocab) if rl else None
                is_total = bool(rl) and all(w in spec.qualifiers or w in ("total", "gesamt", "gross", "brutto") for w in tokens(rl))
                if lv is not None or is_total:
                    good.append((lv[0] if lv else None, p, vl, rl))
            if good:
                for lv, p, vl, rl in good:
                    emit(f, lh, p, "column", ln, label, vl.text.strip(), vl, lv)
                    hits[-1].extra["row"] = rl
                    used.add(id(vl))
                continue
        b = _below(ln, pg, labeler, f, spec, lh.lang, lh.unit)
        if b is not None:
            p = parse_value(f, b.text, spec, lh.lang, lh.unit)
            if p.status != "reject":
                emit(f, lh, p, "below", ln, label, b.text.strip(), b, lh.level)
                used.add(id(b))
    # 3. a project title line: its words say a use and a kind of work
    extra = []
    for h in hits:
        f = spec.fields[h.field]
        if not f.scan_into or h.parsed.status != "value":
            continue
        for tgt in f.scan_into:
            tf = spec.fields[tgt]
            mt = vocab_match(tf, str(h.parsed.value))
            if mt:
                extra.append(Hit(tgt, "building", Parsed("value", mt[0], note=f"scanned in the {h.field} line"), h.page,
                                 "scanned " + h.layout, h.label, h.value_text, h.region, h.lang, h.via, 0.7,
                                 {"scanned_from": h.field}))
    hits += extra
    return hits


def reroute(h: Hit, spec: Spec) -> Hit | None:
    """A category value that is a word of another field's vocabulary and not of its own field's ("CONSTRUCTION TYPE:
    SINGLE FAMILY RESIDENTIAL"): the value is read under the field it belongs to, the label's own field gets no value."""
    f = spec.fields[h.field]
    if f.kind != "category" or f.free or f.internal or h.parsed.status != "value" or h.parsed.canonical and f.values and h.parsed.value in f.values:
        return None
    if h.parsed.note == "coded value":
        return None
    for g in spec.fields.values():
        if g is f or g.kind != "category" or not g.values:
            continue
        mt = vocab_match(g, str(h.value_text))
        if mt and vocab_match(f, str(h.value_text)) is None:
            return Hit(g.name, h.entity, Parsed("value", mt[0], note=f"stated under the label '{h.label}' (a {f.name} label)"),
                       h.page, h.layout, h.label, h.value_text, h.region, h.lang, h.via, 0.55, {"rerouted_from": f.name})
    return None


__all__ = ["Hit", "LabelHit", "make_word_labeler", "read_page", "reroute", "fold"]
