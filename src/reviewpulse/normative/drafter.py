"""Seeding the tree from the clause's own cue words, and the pluggable drafter that completes it.

Two parts, neither of which calls a model by itself:

  cue_seeds(text)      a deterministic CUE ARM. It reads the cue lists of regs/cues.yaml (exception cues, condition cues) and finds, with
                       character spans, the segments of the clause that introduce a condition ("where", "si", "wenn"), an exception
                       ("unless", "sauf", "ausser wenn") or an alternative ("or", "ou", "oder"). No word of any language is in the code
                       except the three "or" words below (the yaml does not separate "and" from "or").
  Drafter(client, ...) the model is a CHOOSER, not a writer. Per node it chooses among enumerated options (which fact, which
                       direction, does the statement hold or not hold) with position balanced voting: the question is asked with the
                       options in several orders and an answer is kept only when the orders agree. A node that cannot be decided is
                       listed in `unresolved` of the obligation (so the compiled rule can never say "satisfied") instead of guessed.

`client` follows the repo convention: `client.complete(system, user_json, json_schema) -> dict`. In tests it is a scripted fake.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..interpreter import units
from ..regs.graph import fold, load_cues
from .schema import Cond, Exc, FactSpec, NormTree, Obligation, SpanRef

OR_WORDS = ("or", "ou", "oder", "and/or", "et/ou", "und/oder")
NONE = "none"
DIRECTIONS = {"ge": "at least (>=)", "le": "at most (<=)", "gt": "more than (>)", "lt": "less than (<)",
              "eq": "exactly equal (==)", "ne": "different from (!=)"}
QUANTITY = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s?([^\W\d_°µ]{1,3}\d?|%|[a-zA-Z]+/[a-zA-Z]+\d?)?(?![\w])")
SYSTEM = ("You help turn one clause of a requirements document (any language) into a checkable rule. You are given a question and a "
          "short list of options. Choose exactly one option. Reply with JSON only.")


@dataclass
class Seed:
    role: str                    # "condition" | "exception" | "alternative"
    cue: str                     # the cue words as written
    cue_span: tuple[int, int]
    span: tuple[int, int]        # the segment the cue introduces (cue included)


def cue_seeds(text: str) -> list[Seed]:
    """Segments of the clause introduced by exception, condition or alternative cues, in reading order, without overlaps."""
    cues = load_cues()
    flat = fold(text)
    hits = [(m.start(), m.end(), "exception") for m in cues.exception_re.finditer(flat)]
    hits += [(m.start(), m.end(), "condition") for m in cues.condition_re.finditer(flat)]
    hits += [(m.start("cue"), m.end("cue"), "exception") for m in cues.exstart_inline_re.finditer(flat)]   # "EXCEPTION: ..." paragraphs
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    seeds: list[Seed] = []
    taken_to = -1
    for start, end, role in hits:
        if start < taken_to:
            continue
        lead = flat[:start].strip()
        stop = re.search(r"[.;]", flat[end:])
        cut = len(flat) if stop is None else end + stop.start()
        if role == "condition" and len(lead) <= 3:            # "Where X, Y must ...": the condition ends at the first comma
            comma = flat.find(",", end)
            if 0 <= comma < cut:
                cut = comma
        later = [h[0] for h in hits if h[2] == "exception" and end <= h[0] < cut]
        if role == "condition" and later:                      # a condition ends where an exception begins
            cut = min(later)
        if cut <= end:
            continue
        seeds.append(Seed(role, text[start:end], (start, end), (start, cut)))
        taken_to = cut
    return seeds


def requirement_spans(text: str, seeds: list[Seed]) -> list[tuple[int, int]]:
    """The parts of the clause that are not a condition or an exception segment."""
    out, pos = [], 0
    for s in sorted(seeds, key=lambda s: s.span[0]):
        if s.span[0] > pos and text[pos:s.span[0]].strip(" ,;"):
            out.append((pos, s.span[0]))
        pos = max(pos, s.span[1])
    if pos < len(text) and text[pos:].strip(" ,;."):
        out.append((pos, len(text)))
    return out


def alternatives(text: str, span: tuple[int, int]) -> list[tuple[int, int]]:
    """Pieces of a span cut at an "or" word; a single piece when there is no cut."""
    flat = fold(text)
    cuts = [m for m in re.finditer(r"(?<![\w/])(" + "|".join(re.escape(w) for w in sorted(OR_WORDS, key=len, reverse=True)) + r")(?![\w/])",
                                   flat[span[0]:span[1]], re.I)]
    if not cuts:
        return [span]
    edges, pos = [], span[0]
    for m in cuts:
        edges.append((pos, span[0] + m.start()))
        pos = span[0] + m.end()
    edges.append((pos, span[1]))
    return [e for e in edges if text[e[0]:e[1]].strip(" ,;.")]


def _reference_re():
    cues = load_cues()
    from ..regs.graph import _alt

    words = list(cues.raw["reference_cues"]) + list(cues.raw["override_cues"])
    return re.compile(rf"(?<![\w])(?:{_alt(words)})[\s(\[]*(?:(?:the|le|la|les|l|el|der|die|das)[\s']+)?$", re.I)


def quantities(text: str, span: tuple[int, int]) -> list[tuple[float, str, int, int]]:
    """(value, unit as written or "1", start, end) of every number in the span. A number that is a label of another clause ("309",
    "315.2.1", "Table 302.6", "comply with 811") is a reference, not a quantity, and is skipped (the cue lists of regs/cues.yaml decide)."""
    cues, ref = load_cues(), _reference_re()
    out = []
    for m in QUANTITY.finditer(text[span[0]:span[1]]):
        start = span[0] + m.start(1)
        raw = m.group(1).replace(",", ".")
        after = text[span[0] + m.end(1):span[0] + m.end(1) + 3]
        if re.match(r"\.\d", after) or raw.count(".") > 1 or after.startswith("/"):
            continue
        before = fold(text[max(0, start - 30):start])
        if ref.search(before) or cues.kind_re.search(before[-16:]):
            continue
        unit = m.group(2) or ""
        keep = unit if unit and units.is_unit(unit) else ""
        end = m.end() if keep else m.end(1)
        out.append((float(raw), keep or "1", start, span[0] + end))
    return out


# ------------------------------------------------------------------------------------------------------------ the chooser
def _ask(client, question: str, order: list[str], options: dict[str, str]) -> str | None:
    shown = {k: options[k] for k in order}
    schema = {"type": "object", "properties": {"choice": {"type": "string", "enum": order}}, "required": ["choice"]}
    try:
        out = client.complete(SYSTEM, json.dumps({"question": question, "options": shown}, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001 - no answer is an abstention, not a verdict
        return None
    got = out.get("choice") if isinstance(out, dict) else None
    return got if got in options else None


def vote(client, question: str, options: dict[str, str], rounds: int = 2, allow_none: bool = True) -> str | None:
    """Position balanced voting: the options are shown in `rounds` different orders (forward, reversed, then rotations); the answer is
    kept only if more than half of the answers agree (with two rounds: both). None means the orders disagreed or no answer came."""
    opts = dict(options)
    if allow_none:
        opts[NONE] = "none of these / the clause does not say"
    keys = list(opts)
    orders = [keys, keys[::-1]] + [keys[i:] + keys[:i] for i in range(1, len(keys))]
    answers = [_ask(client, question, o, opts) for o in orders[:max(rounds, 2)]]
    got = [a for a in answers if a is not None]
    if not got:
        return None
    best = max(set(got), key=got.count)
    return best if got.count(best) * 2 > len(answers) else None


# -------------------------------------------------------------------------------------------------------------- the drafter
class Drafter:
    def __init__(self, client, facts: list[FactSpec], language: str = "en", rounds: int = 2):
        self.client, self.facts, self.language, self.rounds = client, facts, language, rounds
        self.log: list[dict] = []

    def _prior(self, text: str, q: tuple) -> str | None:
        try:
            from ..xeval.verify import _expected_operator, wording

            if self.language not in wording():
                return None
            return _expected_operator(text, q[2], q[3], self.language)
        except Exception:  # noqa: BLE001
            return None

    def _atoms(self, text: str, span: tuple[int, int], pending: list[str], what: str) -> Cond | None:
        """One condition tree for the words in `span`: numbers become limits, other statements become yes/no tests."""
        parts = alternatives(text, span)
        trees = []
        for part in parts:
            atoms = []
            qs = quantities(text, part)
            sentence = text[part[0]:part[1]].strip()
            if qs:
                numeric = {f.name: f.words(self.language) for f in self.facts if f.kind == "number"}
                for q in qs:
                    fact = vote(self.client, f"Which fact does the number {text[q[2]:q[3]]!r} in this part of a clause limit? {sentence}",
                                numeric, self.rounds)
                    if fact in (None, NONE):
                        pending.append(f"{what}: the quantity at {q[2]}:{q[3]} could not be tied to a fact")
                        continue
                    op = vote(self.client, f"In which direction does the clause limit the value {text[q[2]:q[3]]!r}? {sentence}",
                              DIRECTIONS, self.rounds, allow_none=False)
                    prior = self._prior(text, q)
                    if op is None or (prior is not None and prior != op):
                        pending.append(f"{what}: the direction of the limit at {q[2]}:{q[3]} is not settled")
                        continue
                    self.log.append({"fact": fact, "op": op, "span": [q[2], q[3]]})
                    atoms.append((q[2], Cond(kind="test", fact=fact, op=op, value=q[0], unit=q[1], span=SpanRef(start=q[2], end=q[3]))))
            else:
                flags = {f.name: f.words(self.language) for f in self.facts if f.kind == "boolean"}
                fact = vote(self.client, f"Which yes/no fact does this part of a clause state? {sentence}", flags, self.rounds)
                if fact in (None, NONE):
                    pending.append(f"{what}: no yes/no fact is stated at {part[0]}:{part[1]}")
                else:
                    holds = vote(self.client, f"Does the clause say the fact holds or that it does not hold? {sentence}",
                                 {"holds": "the fact holds", "not_holds": "the fact does not hold"}, self.rounds, allow_none=False)
                    if holds is None:
                        pending.append(f"{what}: polarity at {part[0]}:{part[1]} is not settled")
                    else:
                        atoms.append((part[0], Cond(kind="test", fact=fact, op="eq", value=holds == "holds",
                                                    span=SpanRef(start=part[0], end=part[1]))))
            if atoms:
                conds = [c for _, c in sorted(atoms, key=lambda t: t[0])]
                trees.append(conds[0] if len(conds) == 1 else Cond(kind="all", args=conds, span=SpanRef(start=part[0], end=part[1])))
        if not trees:
            return None
        return trees[0] if len(trees) == 1 else Cond(kind="any", args=trees, span=SpanRef(start=span[0], end=span[1]))

    def draft(self, text: str, clause_id: str = "c1", document: str = "unknown") -> NormTree | None:
        """A tree for one atomic obligation, or None when no requirement could be decided (nothing is guessed)."""
        seeds = cue_seeds(text)
        pending: list[str] = []
        applic = [self._atoms(text, (s.cue_span[1], s.span[1]), pending, "condition") for s in seeds if s.role == "condition"]
        excs = [(s, self._atoms(text, (s.cue_span[1], s.span[1]), pending, "exception")) for s in seeds if s.role == "exception"]
        req_parts = [self._atoms(text, sp, pending, "requirement") for sp in requirement_spans(text, seeds)]
        req_parts = [r for r in req_parts if r is not None]
        if not req_parts:
            return None
        requirement = req_parts[0] if len(req_parts) == 1 else Cond(kind="all", args=req_parts)
        app = [a for a in applic if a is not None]
        modality = vote(self.client, f"Does the clause require what its main part states, or forbid it? {text[:400]}",
                        {"require": "it requires what is stated", "forbid": "it forbids what is stated (must not, may not, no ...)"},
                        self.rounds, allow_none=False)
        if modality is None:
            pending.append("modality: require or forbid is not settled")
        ob = Obligation(
            id="o1", requirement=requirement, modality="prohibition" if modality == "forbid" else "obligation",
            applicability=None if not app else (app[0] if len(app) == 1 else Cond(kind="all", args=app)),
            exceptions=[Exc(when=c, cue=s.cue, span=SpanRef(start=s.span[0], end=s.span[1])) for s, c in excs if c is not None],
            span=SpanRef(start=0, end=len(text)), unresolved=pending)
        used = {n.fact for n in _walk(ob) if n.kind == "test"}
        return NormTree(clause_id=clause_id, text=text, language=self.language, document=document,
                        facts=[f for f in self.facts if f.name in used], obligations=[ob])


def _walk(ob: Obligation):
    from .schema import cond_nodes

    return cond_nodes(ob)
