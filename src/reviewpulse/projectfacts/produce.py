"""Project facts as Candidates of the evidence ledger, and a producer that answers fact requests by meaning."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..drawingset.model import DrawingSet
from ..drawingset.pagedata import PageData
from ..drawingset.views import find_title_block, owner_of
from ..drawingset.vocab import load_vocab
from ..interpreter.schema import Binding
from ..ledger.candidate import Candidate
from ..ledger.producer import meaning_score
from ..ledger.request import FactRequest
from .embed import make_embedding_labeler
from .read import Hit, read_page, reroute
from .spec import Spec, load_spec

NAME = "project_facts"
FAMILY = "textlayer"                  # the words arm and the embedding arm read the same text layer: one family
LAYOUT_SCORE = {"same line": 0.85, "right": 0.85, "inline": 0.8, "column": 0.8, "below": 0.72, "statement": 0.7}
BINDING_KIND = {"number": "number", "bool": "boolean", "category": "string"}


@dataclass
class ProjectFacts:
    candidates: list[Candidate] = field(default_factory=list)      # values read, and fields stated as unknown (value None)
    unknown: dict[str, str] = field(default_factory=dict)          # field -> why nothing was read
    hits: list[Hit] = field(default_factory=list)
    n_sheets: int = 0
    arm: str = "words"

    def stated(self) -> dict[str, object]:
        """The best value per building level field: highest score, ties to the first sheet."""
        out: dict[str, Candidate] = {}
        for c in self.candidates:
            if c.value is not None and c.entity == "building" and (c.fact not in out or c.score > out[c.fact].score):
                out[c.fact] = c
        return {k: c.value for k, c in out.items()}

    def requests(self, spec: Spec | None = None) -> list[FactRequest]:
        """A question for every field the set leaves unknown, to be asked of a person later."""
        spec = spec or load_spec()
        out = []
        for name, why in self.unknown.items():
            f = spec.fields[name]
            out.append(FactRequest(entity="building", entity_kind="building", fact=name, kind=f.kind, unit=f.unit if f.kind == "number" else "1",
                       words=f.description, reason="missing", why=why))
        return out


def bindings(spec: Spec | None = None) -> dict[str, Binding]:
    spec = spec or load_spec()
    out = {}
    for f in spec.fields.values():
        if f.internal:
            continue
        out[f.name] = Binding(kind=BINDING_KIND[f.kind], unit=f.unit if f.kind == "number" else "1", description=f.description)
        if f.by_level:
            out["floor_area"] = Binding(kind="number", unit="m2", description="Floor area of one level")
    return out


def _candidate(h: Hit, pg: PageData, ds: DrawingSet | None, vocab) -> Candidate:
    sheet = f"P{pg.index + 1}"
    view = ""
    where = ""
    if ds is not None:
        sh = next((s for s in ds.sheets if s.index == pg.index), None)
        if sh:
            sheet = sh.key
            cx, cy = (h.region[0] + h.region[2]) / 2, (h.region[1] + h.region[3]) / 2
            v = owner_of(cx, cy, sh.views)
            if v:
                view = v.id
                where = f", view '{v.title}'" if v.title else f", view {v.id}"
    tb, _ = find_title_block(pg, vocab)
    if tb is not None and tb[0] <= (h.region[0] + h.region[2]) / 2 <= tb[2] and tb[1] <= (h.region[1] + h.region[3]) / 2 <= tb[3]:
        where += ", title block"
    p = h.parsed
    base = LAYOUT_SCORE.get(h.layout, 0.6) if h.layout in LAYOUT_SCORE else 0.6
    score = base * (h.label_score if h.via == "embedding" else 1.0)
    if p.status == "value" and not p.canonical:
        score = min(score, 0.5)
    if "rerouted_from" in h.extra:
        score = min(score, 0.55)
    if p.status == "unstated":
        score = 0.5
    shown = f"'{h.label}' -> '{h.value_text}'" if h.label else f"'{h.value_text}'"
    source = f"sheet {sheet}{where}, {h.layout}: {shown}"
    fact = "floor_area" if (h.field == "gross_floor_area" and h.entity.startswith("level:")) else h.field
    f_unit = p.unit if p.status == "value" and isinstance(p.value, (int, float)) and not isinstance(p.value, bool) else "1"
    return Candidate(entity=h.entity, fact=fact, value=p.value if p.status == "value" else None, unit=f_unit, kind="stated",
                     source=source, sheet=sheet, view=view, region=tuple(round(x, 1) for x in h.region),
                     words=f"{h.label}: {h.value_text}" if h.label else h.value_text, producer=NAME, family=FAMILY,
                     score=round(min(1.0, max(0.0, score)), 3))


def read_project_facts(pages: list[PageData], ds: DrawingSet | None = None, spec: Spec | None = None, embedder=None,
                       arm: str | None = None) -> ProjectFacts:
    """Project facts of a set from its text layer. `embedder` (a function texts -> vectors) turns on the second arm; without
    one the arm is words only. Fields the set does not state are in `unknown` and in `candidates` as value None."""
    spec = spec or load_spec()
    vocab = load_vocab()
    labeler = make_embedding_labeler(spec, vocab, embedder) if embedder is not None else None
    out = ProjectFacts(n_sheets=len(pages), arm=arm or ("words+embedding" if embedder is not None else "words"))
    seen: dict[tuple, Candidate] = {}
    n_lines = sum(len(p.lines) for p in pages)
    for pg in pages:
        for h in read_page(pg, spec, vocab, labeler):
            rr = reroute(h, spec)
            if rr is not None:
                out.hits.append(h)
                out.hits.append(rr)
                out.candidates.append(Candidate(entity=h.entity, fact=h.field, value=None, kind="stated",
                                                source=f"sheet P{pg.index + 1}: '{h.label}' holds '{h.value_text}', a "
                                                       f"{rr.field.replace('_', ' ')} word, not a {h.field.replace('_', ' ')}",
                                                producer=NAME, family=FAMILY, score=0.3, words=h.value_text))
                h = rr
            else:
                out.hits.append(h)
            if spec.fields[h.field].internal:
                continue
            c = _candidate(h, pg, ds, vocab)
            key = (c.entity, c.fact, c.value, c.unit)
            if key in seen:
                seen[key].words += f" | also sheet {c.sheet}" if "also sheet" not in seen[key].words else f", {c.sheet}"
                continue
            seen[key] = c
            out.candidates.append(c)
    got = {c.fact for c in out.candidates if c.value is not None and c.entity == "building"}
    got |= {"gross_floor_area" for c in out.candidates if c.fact == "floor_area" and c.value is not None}
    stated_unknown = {c.fact for c in out.candidates if c.value is None and c.score >= 0.5}
    for name, f in spec.fields.items():
        if f.internal or name in got:
            continue
        if name in stated_unknown:
            why = "the set names the field but gives no value (to be determined, or no unit)"
        elif not any(p.has_text_layer and p.lines for p in pages):
            why = "no text layer in the set: nothing was read (a scan needs OCR first)"
        else:
            why = f"no label for it in {len(pages)} sheets ({n_lines} text lines)"
        out.unknown[name] = why
        if name not in stated_unknown:
            out.candidates.append(Candidate(entity="building", fact=name, value=None, unit="1", kind="stated",
                                            source=why, producer=NAME, family=FAMILY, score=0.0))
    return out


class ProjectFactsProducer:
    """Answers fact requests for project facts. Protocol of `ledger.producer.Producer`."""

    name = NAME
    family = FAMILY

    def __init__(self, facts: ProjectFacts, extra: list[Candidate] | None = None):
        self.facts = facts
        self.candidates = list(facts.candidates) + list(extra or [])
        self.bindings = bindings()

    def _names(self, request: FactRequest) -> list[tuple[str, float]]:
        out = []
        for name, b in self.bindings.items():
            s = meaning_score(request, name, b)
            if s >= 1.0:
                out.append((name, 1.0 if name == request.fact else 0.8))
        return out

    def holds(self, request: FactRequest) -> float:
        if request.entity not in (None, "building") and not (request.entity or "").startswith("level:"):
            return 0.0
        return max((s for _, s in self._names(request)), default=0.0)

    def answer(self, request: FactRequest) -> list[Candidate]:
        names = {n for n, _ in self._names(request)}
        out = []
        for c in self.candidates:
            if c.fact in names and (request.entity is None or c.entity == request.entity):
                out.append(c)
        return out
