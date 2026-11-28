"""The regulation graph: sections, definitions, tables and exceptions of a requirement document as nodes, and the references
between them as typed edges, resolved by rules before any model reads a clause.

    graph = build_graph(full_text, clauses)            # clauses from rules.clauses.split_document / split_cached
    ctx = resolve_context(graph, "3.79")               # what a model needs next to clause 3.79
    ctx.references, ctx.definitions, ctx.tables, ctx.exceptions, ctx.conditions, ctx.unresolved

Edge semantics, one direction for every type: an edge `type` runs from a PROVIDER to a CONSUMER, and says what the provider
gives the consumer.

    reference     the cited clause            -> the clause that cites it ("see 3.4")
    table_of      the table                   -> the clause that cites it ("see Table B4")
    definition_of the definition of a term    -> the clause that uses the term ("as defined in 2.1", or the term itself)
    exception_of  the exception               -> the clause it limits ("except as provided in 1011.5", "Exception 1.", "unless ...")
    condition_from the clause that holds the condition -> the clause that depends on it ("where the conditions of 4.2 are met")

Every edge keeps its evidence: the clause and the character span (in the document text) where it was read, the cue words that
decided its type, and a short reason. Nothing here calls a model, and nothing is guessed: a reference that cannot be tied to
exactly one place is kept as unresolved, external (it names another document) or ambiguous, never dropped and never forced.
All words that belong to a language are in `cues.yaml`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CUES_FILE = Path(__file__).with_name("cues.yaml")
TABLE_CLAUSES = ("table_row", "table_header")


# ---------------------------------------------------------------------------------------------------------------- cues
def fold(s: str) -> str:
    """Accent folding that keeps every offset: one character in, one character out (so spans carry over to the original)."""
    out = []
    for ch in s:
        if ch in "’‘ʼ`":
            out.append("'")
        elif ch in "\u2010\u2011\u2012\u2013\u2014\u2212":
            out.append("-")
        elif ch == " " or ch == " ":
            out.append(" ")
        elif ord(ch) > 127:
            d = unicodedata.normalize("NFD", ch)
            out.append(d[0] if d and not unicodedata.combining(d[0]) else ch)
        else:
            out.append(ch)
    return "".join(out)


def _phrase(cue: str) -> str:
    words = [re.escape(w) for w in fold(cue).lower().replace("'", " ").split()]
    return r"[\s']+".join(words)


def _alt(cues: Iterable[str]) -> str:
    return "|".join(_phrase(c) for c in sorted(set(cues), key=lambda c: (-len(c), c)))


def _word_alt(words: Iterable[str]) -> str:
    return "|".join(re.escape(fold(w).lower()) for w in sorted(set(words), key=lambda w: (-len(w), w)))


@dataclass
class Cues:
    raw: dict
    kind_of: dict[str, str]
    kind_re: re.Pattern
    ref_re: re.Pattern
    bare_re: re.Pattern
    label_re: re.Pattern
    exception_re: re.Pattern
    exception_ref_re: re.Pattern
    refcue_end_re: re.Pattern
    override_re: re.Pattern
    condition_re: re.Pattern
    modal_re: re.Pattern
    defref_re: re.Pattern
    defcue_re: re.Pattern
    weak_defcues: set[str]
    defheading_re: re.Pattern
    exstart_re: re.Pattern
    exstart_inline_re: re.Pattern
    annotation_re: re.Pattern
    unit_re: re.Pattern
    ext_after_re: re.Pattern
    ext_before_re: re.Pattern
    term_stop: set[str]
    letter_kinds: set[str]
    conj_re: str
    range_re: str


_CACHE: dict[str, Cues] = {}


def load_cues(path: str | Path | None = None, extra: dict | None = None) -> Cues:
    """Compile the cue file. `extra` adds words to a list (a new language, or a project's own words) without editing the file."""
    key = f"{path}|{sorted((extra or {}).items(), key=str)}"
    if key in _CACHE:
        return _CACHE[key]
    raw = yaml.safe_load(Path(path or CUES_FILE).read_text(encoding="utf-8"))
    for k, v in (extra or {}).items():
        if isinstance(v, dict):
            raw.setdefault(k, {})
            for kk, vv in v.items():
                raw[k][kk] = list(raw[k].get(kk, [])) + list(vv)
        else:
            raw[k] = list(raw.get(k, [])) + list(v)
    kind_of: dict[str, str] = {}
    for kind, words in raw["kinds"].items():
        for w in words:
            kind_of[fold(w).lower()] = kind
    kinds = _word_alt(kind_of)
    # a label: "3.79", "206.2.8", "R. 111-19-1", "B4", "1011.5(b)", "35.151 (a)(2)"; a lone capital letter for kinds that allow it
    num = r"(?-i:[A-Z]{1,2}\.?\s?)?\d+(?:[.\-]\d+)*(?:\s?\([A-Za-z0-9]{1,4}\))*"
    sub = r"\(\s*(?!(?:s|es)\s*\))[A-Za-z0-9]{1,4}\s*\)"
    letter = r"(?-i:[A-Z]|[IVX]{2,5})(?![A-Za-z\d])"          # "Appendix C", "annexe III"
    conj = _word_alt(raw["conjunctions"])
    rng = _word_alt(raw["range_words"])
    numw = _word_alt(raw["number_words"])
    label = rf"(?:{num}|{sub})"
    label_any = rf"(?:{num}|{sub}|{letter})"
    chain = rf"(?:\s*,\s*|\s*;\s*|\s+(?:{conj})\s+|\s*,\s*(?:{conj})\s+|\s+(?:{rng})\s+|\s*[-]\s*)(?:{label})"
    ref_re = re.compile(rf"(?<![\w])(?P<kind>{kinds})\.?\s*(?:(?:{numw})\.?\s*)?(?P<first>{label_any})(?P<more>(?:{chain})*)", re.I)
    cues_alt = _alt(list(raw["reference_cues"]) + list(raw["override_cues"]) + list(raw["exception_cues"]) + list(raw.get("exception_ref_cues", [])) + list(raw["definition_ref_cues"]))
    bare_re = re.compile(rf"(?<![\w])(?P<cue>{cues_alt})\s+(?:also\s+)?(?P<first>{num})(?P<more>(?:{chain})*)", re.I)
    ext_phrases = _alt(raw["external_nouns"])
    conn = _alt(raw["external_connectors"])
    prefixes = "|".join(re.escape(p) for p in raw["standard_prefixes"])
    ext_after = re.compile(rf"^\s*(?:,\s*)?(?:(?:{conn})[\s']+)+(?:(?:the|la|le|les|der|die|das|el|los|las|this|present|presente|ce|cette|dieses|este|esta)[\s']+)?"
                           rf"(?:[\w']+\s+){{0,3}}?(?:(?:{ext_phrases})\b|(?-i:{prefixes})\b)", re.I)
    ext_before = re.compile(rf"(?:(?-i:{prefixes})|(?-i:[A-Z]{{2,}}(?:-[A-Z]+)*)|(?:{ext_phrases}))\s*$", re.I)
    exs = _alt(raw["exception_starts"])
    c = Cues(
        raw=raw, kind_of=kind_of, kind_re=re.compile(rf"(?<![\w])(?:{kinds})\b", re.I), ref_re=ref_re, bare_re=bare_re,
        label_re=re.compile(label_any),
        exception_re=re.compile(rf"(?<![\w])(?:{_alt(raw['exception_cues'])})(?![\w])", re.I),
        exception_ref_re=re.compile(rf"(?<![\w])(?:{_alt(list(raw['exception_cues']) + list(raw.get('exception_ref_cues', [])))})(?![\w])", re.I),
        refcue_end_re=re.compile(rf"(?<![\w])(?:{_alt([c for c in raw['reference_cues'] if c not in set(raw.get('weak_reference_cues', []))])})[\s(\[]*(?:(?:the|le|la|les|l|el|la|los|las|der|die|das|dem|den|un|une)[\s']+)?$", re.I),
        override_re=re.compile(rf"(?<![\w])(?:{_alt(raw['override_cues'])})(?![\w])", re.I),
        condition_re=re.compile(rf"(?<![\w])(?:{_alt(raw['condition_cues'])})(?![\w])", re.I),
        modal_re=re.compile(rf"(?<![\w])(?:{_alt(raw['modals'])})(?![\w])", re.I),
        defref_re=re.compile(rf"(?<![\w])(?:{_alt(raw['definition_ref_cues'])})(?:[\s']+(?:the|le|la|les|l|der|die|das|el|los|las))?[\s']*$", re.I),
        defcue_re=re.compile(rf"\s+(?P<cue>{_alt(raw['definition_cues'])})(?![\w])", re.I),
        weak_defcues={fold(w).lower() for w in raw["weak_definition_cues"]},
        defheading_re=re.compile(rf"(?<![\w])(?:{_alt(raw['definition_headings'])})(?![\w])", re.I),
        exstart_re=re.compile(rf"^\W*(?:\(?[\w.\-]{{1,12}}\)?\s+){{0,2}}?(?P<cue>{exs})", re.I),
        exstart_inline_re=re.compile(rf"(?:(?<=\n)|(?<=[.!?:;]\s)|(?<=[.!?:;]\n))\s*(?P<cue>{exs})\b[ \t]*\d*[ \t]*[.:)]", re.I),
        annotation_re=re.compile(rf"^\W*(?:{_word_alt(raw['annotation_prefixes'])})\b\s*", re.I),
        unit_re=re.compile(rf"^\s*(?:{_word_alt(raw['unit_words'])})(?![A-Za-z])", re.I),
        ext_after_re=ext_after, ext_before_re=ext_before,
        term_stop={fold(w).lower() for w in raw["term_stop"]}, letter_kinds=set(raw["letter_label_kinds"]),
        conj_re=conj, range_re=rng,
    )
    _CACHE[key] = c
    return c


# ---------------------------------------------------------------------------------------------------------------- model
@dataclass
class Node:
    id: str                          # the clause id, or "def:<term>@<clause>" / "exc:<clause>#<n>" for nodes that are a span
    ntype: str                       # clause | table | definition | exception
    start: int
    end: int
    clause: str                      # the clause that holds the node
    labels: list[tuple[str, str]] = field(default_factory=list)       # (kind, label) it can be cited by: ("article", "5")
    local: str = ""                  # label that only means something inside a scope: "(b)", "2", "iii"
    scope: str | None = None         # the clause that is the scope of a local label
    term: str = ""
    cue: str = ""


@dataclass
class Edge:
    type: str                        # reference | table_of | definition_of | exception_of | condition_from
    provider: str | None             # node id that gives; None while unresolved
    consumer: str                    # node id (a clause) that receives
    evidence_clause: str             # the clause where the words were read
    start: int                       # span of the words in the document text
    end: int
    quote: str
    cue: str = ""
    reason: str = ""
    status: str = "resolved"         # resolved | first_of_many | group | partial | unresolved | external
    cited: str = ""                  # the reference as written ("Table B4")
    candidates: list[str] = field(default_factory=list)
    origin: str = "ref"              # ref (a cited label) | exception (a clause or sentence that states an exception) | term (a defined term used)


@dataclass
class Graph:
    text: str
    clauses: list
    nodes: dict[str, Node]
    edges: list[Edge]
    cues: Cues
    by_consumer: dict[str, list[Edge]] = field(default_factory=dict)
    by_provider: dict[str, list[Edge]] = field(default_factory=dict)
    terms: dict[str, list[Node]] = field(default_factory=dict)
    clause_by_id: dict = field(default_factory=dict)

    def index(self) -> None:
        self.by_consumer, self.by_provider = {}, {}
        for e in self.edges:
            self.by_consumer.setdefault(e.consumer, []).append(e)
            if e.provider:
                self.by_provider.setdefault(e.provider, []).append(e)

    def stats(self) -> dict:
        resolved = [e for e in self.edges if e.provider]
        out = {"nodes": len(self.nodes), "edges": len(resolved)}
        for t in ("reference", "table_of", "definition_of", "exception_of", "condition_from"):
            out[t] = sum(1 for e in resolved if e.type == t)
        out["unresolved"] = sum(1 for e in self.edges if e.status == "unresolved")
        out["external"] = sum(1 for e in self.edges if e.status == "external")
        return out


# ---------------------------------------------------------------------------------------------------------------- labels
def norm_label(s: str) -> tuple[str, list[str]]:
    """'1011.5 (b)(2)' -> ('1011.5', ['b', '2']); 'R. 111-19-1' -> ('r111-19-1', []); '(b)' -> ('', ['b'])."""
    s = fold(s).strip().lower()
    subs = re.findall(r"\(\s*([a-z0-9]{1,4})\s*\)", s)
    base = re.sub(r"\(.*", "", s)
    base = re.sub(r"[\s.]+$", "", base)
    base = re.sub(r"^([a-z]{1,2})\.\s*", r"\1", base)
    return base.replace(" ", ""), subs


def _split_chain(first: str, more: str, cues: Cues) -> list[tuple[str, int, int, str]]:
    """Items of a reference list with their offsets inside `first + more`: (label text, start, end, joiner that came before)."""
    items = [(first, 0, len(first), "")]
    pos = len(first)
    for m in re.finditer(rf"(?P<j>\s*,\s*|\s*;\s*|\s+(?:{cues.conj_re})\s+|\s*,\s*(?:{cues.conj_re})\s+|\s+(?:{cues.range_re})\s+|\s*-\s*)"
                         rf"(?P<l>{cues.label_re.pattern})", more, re.I):
        items.append((m.group("l"), pos + m.start("l"), pos + m.end("l"), m.group("j").strip().lower()))
    return items


@dataclass
class _Ref:
    kind: str                        # canonical kind or "" for a bare cue
    label: str
    start: int
    end: int
    cue: str
    joiner: str


class _Builder:
    def __init__(self, text: str, clauses: list, cues: Cues):
        self.text, self.clauses, self.cues = text, clauses, cues
        self.ft = fold(text)
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.by_id = {c.id: c for c in clauses}
        self.glob: dict[tuple[str, str], list[str]] = {}          # (kind class, label) -> clause ids
        self.local: dict[tuple[str, str], list[str]] = {}         # (scope clause, local label) -> clause ids
        self.order = {c.id: i for i, c in enumerate(clauses)}
        self.terms: dict[str, list[Node]] = {}
        self.in_glossary: set[str] = set()
        self._anchors: dict | None = None
        self._starts: list | None = None
        self.caption_starts: set[int] = set()            # offsets of the caption lines of tables: they name a table, they do not cite it
        self._rows: list = []

    # ------------------------------------------------------------------------------------------ nodes
    def own_labels(self, c) -> tuple[list[tuple[str, str]], str]:
        """What a clause can be cited as: from its caption or its first words. Returns (global labels, local label)."""
        cues = self.cues
        labels, local = [], ""
        if c.kind == "table_row":
            return labels, local                          # a row of a table is never a part that is cited
        if c.kind == "subitem" and re.match(r"\s*[-•\u2013*▪●]\s", c.text):
            return labels, local                          # a bullet that happens to start with a label is a fragment, not a part
        head = fold(c.text[:90])
        ann = ""
        m = cues.annotation_re.match(head)
        if m:
            ann = "annotation"
            head = head[m.end():]
        mt = re.match(rf"\W*(?P<kind>{_word_alt(cues.kind_of)})\.?\s*(?:(?:{_word_alt(cues.raw['number_words'])})\.?\s*)?(?P<label>{cues.label_re.pattern})", head, re.I)
        if mt:
            kind = cues.kind_of[mt.group("kind").lower()]
            lab, subs = norm_label(mt.group("label"))
            if lab:
                labels.append((ann or kind, lab))
            elif subs:
                local = subs[-1]
        else:
            mn = re.match(r"\W{0,3}(?P<label>(?-i:[A-Z]{1,2}\.?\s?)?\d+(?:[.\-]\d+)+|(?-i:[A-Z]{1,2})\d+(?:[.\-]\d+)*)(?:\s?\((?P<sub>[A-Za-z0-9]{1,4})\))?(?=[\s.:\-)\]]|$)", head)
            if mn:
                lab, _ = norm_label(mn.group("label"))
                labels.append((ann or "clause", lab))
            else:
                ml = re.match(r"\W{0,2}\(?(?P<l>[a-z]{1,2}|\d{1,3}|[ivxl]{1,5})\s*[.)]\s", head)
                if ml and c.kind in ("numbered", "subitem", "paragraph", "article"):
                    local = ml.group("l").lower()
                elif c.kind in ("numbered", "article") and re.match(r"\W{0,2}\d{1,4}[.)]?\s", head):
                    local = re.match(r"\W{0,2}(\d{1,4})", head).group(1)
        # a caption kept in the id of the clause: "Table B4", "Art. 5", "§ 35.151"
        mi = re.match(rf"(?P<kind>{_word_alt(cues.kind_of)})\.?\s*(?P<label>{cues.label_re.pattern})\s*$", fold(c.id), re.I)
        if mi:
            kind = cues.kind_of[mi.group("kind").lower()]
            lab, _ = norm_label(mi.group("label"))
            if lab and kind != "paragraph" and c.id[:1].isupper() and (kind, lab) not in labels:
                labels.append((kind, lab))
        return labels, local

    def caption_above(self, c) -> str:
        """The label of a caption line that sits right above a table the splitter could not name."""
        pat = re.compile(rf"(?m)^[ \t]*(?P<kind>{_word_alt(self.cues.kind_of)})\.?[ \t]*(?P<label>{self.cues.label_re.pattern})[^\n]*$", re.I)
        before = self.ft[max(0, c.start - 300):c.start]
        last = None
        for m in pat.finditer(before):
            last = m
        if last is None or self.cues.kind_of[last.group("kind").lower()] != "table":
            return ""
        if len(before[last.end():].strip()) > 0:                      # something other than blank lines between caption and table
            return ""
        self.caption_starts.add(max(0, c.start - 300) + last.start("kind"))
        return norm_label(last.group("label"))[0]

    def make_nodes(self) -> None:
        container: str | None = None
        for c in self.clauses:
            labels, local = self.own_labels(c)
            if c.kind == "table_header" and not any(k == "table" for k, _ in labels):
                cap = self.caption_above(c)           # a table written under its caption line ("Table 1.2 Maximum distance")
                if cap:
                    labels.append(("table", cap))
            ntype = "table" if (c.kind == "table_header" and any(k == "table" for k, _ in labels)) else "clause"
            n = Node(c.id, ntype, c.start, c.end, c.id, labels, local, None)
            if local:
                n.scope = c.parent or container
                if n.scope:
                    self.local.setdefault((n.scope, local), []).append(c.id)
            if labels and c.kind not in TABLE_CLAUSES:
                container = c.id
            elif c.kind == "table_header" and labels:
                pass
            self.nodes[c.id] = n
            for kind, lab in labels:
                self.glob.setdefault((kind, lab), []).append(c.id)
        # a table's span covers its rows
        last_row: dict[str, int] = {}
        for c in self.clauses:
            if c.kind == "table_row" and c.parent in self.nodes:
                last_row[c.parent] = max(last_row.get(c.parent, 0), c.end)
        for tid, end in last_row.items():
            self.nodes[tid].end = max(self.nodes[tid].end, end)

    # ------------------------------------------------------------------------------------------ resolution
    def prefer(self, kind: str, ids: list[str]) -> list[str]:
        """Several clauses carry one label: keep the one that IS the part. A table cited is the table, not a row that repeats its name;
        a clause the splitter had to rename to keep ids unique ("Diagram 5.2 [Flats 3.6]") is the same part continued."""
        if len(ids) < 2:
            return ids
        if kind == "table":
            tables = [i for i in ids if self.nodes[i].ntype == "table"]
            ids = tables or ids
        rows = [i for i in ids if self.by_id[i].kind == "table_row"]
        ids = [i for i in ids if i not in rows] or ids
        head = ids[0]
        if all(i.startswith(head + " [") or i.startswith(head + " (") for i in ids[1:]) and not self.by_id[head].kind == "subitem":
            return [head]
        return ids

    def lookup_global(self, kind: str, lab: str) -> list[str]:
        """Clause ids that carry the global label `lab`, for a reference of kind `kind` ('' for a bare cue)."""
        out: list[str] = []
        for (k, lb), ids in self.glob.items():
            if lb != lab or k == "annotation" or k == "advisory":
                continue
            if kind == "table" and k != "table":
                continue
            if kind == "figure" and k != "figure":
                continue
            if kind == "appendix" and k not in ("appendix",):
                continue
            if kind in ("section", "article", "paragraph", "") and k in ("table", "figure", "regulation"):
                continue
            if kind == "regulation" and k in ("table", "figure", "appendix"):
                continue
            out.extend(ids)
        return sorted(set(out), key=self.order.get)

    def anchor(self, kind: str, lab: str) -> tuple[str, int] | None:
        """A label at the start of a line that the splitter left inside a clause: (the clause, the offset)."""
        if kind == "appendix" and lab[:1].isdigit():
            return None
        if self._anchors is None:
            cues = self.cues
            pat = re.compile(rf"(?m)^[ 	]*(?:(?P<kind>{_word_alt(cues.kind_of)})\.?[ 	]*)?(?P<label>{cues.label_re.pattern})(?=[ 	]|$)", re.I)
            rows = [(c.start, c.end, c.id) for c in self.clauses if c.kind not in TABLE_CLAUSES]
            starts = [r[0] for r in rows]
            self._anchors = {}
            import bisect
            for m in pat.finditer(self.ft):
                lab_n, subs = norm_label(m.group("label"))
                if not lab_n or subs or not re.search(r"\d", lab_n):
                    continue
                if not m.group("kind") and not re.fullmatch(r"[a-z]{1,2}\d+(?:[.\-]\d+)*|\d+(?:[.\-]\d+)+", lab_n):
                    continue
                i = bisect.bisect_right(starts, m.start("label")) - 1
                if i < 0 or rows[i][1] <= m.start("label"):
                    continue
                k = self.cues.kind_of[m.group("kind").lower().rstrip(".")] if m.group("kind") else ""
                self._anchors.setdefault((k, lab_n), (rows[i][2], m.start("label")))
        if kind in ("table", "figure"):
            return self._anchors.get((kind, lab))
        for k in (kind, "", "article", "section", "paragraph", "appendix"):
            if (k, lab) in self._anchors:
                return self._anchors[(k, lab)]
        return None

    def group(self, kind: str, lab: str) -> list[str]:
        """A virtual node: every clause whose label continues `lab` ("Section 3" is the clauses numbered 3.x)."""
        if kind in ("table", "figure", "regulation") or (kind == "appendix" and lab[:1].isdigit()):
            return []                                         # "Schedule 4", "Part 24": numbered parts of other documents, not appendices here
        sep = r"[.\-]" if lab[-1:].isdigit() else r"(?=\d)"
        pat = re.compile(rf"^{re.escape(lab)}{sep}") if sep != r"(?=\d)" else re.compile(rf"^{re.escape(lab)}\d")
        ids = [cid for (k, lb), cs in self.glob.items() if k not in ("annotation", "regulation", "table", "figure") and pat.match(lb) for cid in cs]
        return sorted(set(ids), key=self.order.get)

    def resolve(self, src, kind: str, label_text: str) -> tuple[str, list[str], str]:
        lab, subs = norm_label(label_text)
        if not lab:                                           # "(b)": local to the citing clause
            return self.resolve_local(src, subs)
        ids = self.prefer(kind, self.lookup_global(kind, lab))
        if not ids:
            ids = [i for i in self.resolve_local(src, [lab])[1]] if re.fullmatch(r"\d{1,3}|[a-z]{1,2}", lab) and kind == "paragraph" else []
            if ids:
                return ("resolved" if len(ids) == 1 else "first_of_many"), ids[:1], "label found inside the citing clause's scope"
            g = self.group(kind, lab)
            if g:
                return "group", g, f"no clause carries {lab} itself; {len(g)} clauses are numbered under it"
            a = self.anchor(kind, lab)
            if a:
                return "anchor", [a[0]], f"{lab} starts a line inside clause {a[0]} (the splitter did not cut a clause there)"
            return "unresolved", [], "no clause or table carries this label"
        status, note = ("resolved", "") if len(ids) == 1 else ("first_of_many", f"{len(ids)} clauses carry this label; the first one is taken")
        target = ids[0]
        if subs:
            kids = [c for c in self.clauses if c.parent == target]
            hit = None
            for s in subs[:1]:
                hit = next((c for c in kids if self.nodes[c.id].local == s), None)
            if hit:
                return status, [hit.id], (note + " " if note else "") + f"sub-item ({subs[0]}) found under it"
            return "partial", [target], f"{lab} found, its sub-item ({subs[0]}) was not found as a clause"
        return status, ids[:1] if status == "resolved" else ids, note

    def resolve_local(self, src, subs: list[str]) -> tuple[str, list[str], str]:
        if not subs:
            return "unresolved", [], "empty label"
        s = subs[0].lower()
        scopes: list[str] = [src.id]
        if src.parent:
            scopes.append(src.parent)
        sc = self.nodes[src.id].scope
        while sc and sc not in scopes:
            scopes.append(sc)
            sc = self.nodes[sc].scope if sc in self.nodes else None
        for scope in scopes:
            hits = self.local.get((scope, s), [])
            hits = [h for h in hits if h != src.id]
            if len(hits) == 1:
                return "resolved", hits, f"local label ({s}) inside {scope}"
            if len(hits) > 1:
                return "first_of_many", hits[:1], f"local label ({s}) occurs {len(hits)} times inside {scope}"
        return "unresolved", [], f"no local label ({s}) in the clause or the clauses around it"

    def is_external(self, start: int, end: int) -> str:
        after = self.ft[end:end + 70]
        if self.cues.ext_after_re.match(after):
            return "followed by the name of another document"
        before = self.ft[max(0, start - 40):start]
        if self.cues.ext_before_re.search(before):
            return "preceded by the name of another document or standard"
        return ""

    # ------------------------------------------------------------------------------------------ edges
    def cue_window(self, c, start: int) -> tuple[str, int]:
        """The words of the same sentence before a reference."""
        lo = max(c.start, start - 160)
        w = self.ft[lo:start]
        cut = max((m.end() for m in re.finditer(r"[.;:!?](?=\s)|\n\s*\n", w)), default=0)
        return w[cut:], lo + cut

    def classify(self, c, start: int, kind: str, bare_cue: str) -> tuple[str, str, str]:
        """(edge type, cue, direction) for a reference at `start`."""
        win, _ = self.cue_window(c, start)
        cues = self.cues
        m = None
        for mm in cues.override_re.finditer(win):
            m = mm
        if m:
            return "exception_of", m.group(0), "consumer_excepts_cited"
        m = None
        for mm in cues.exception_ref_re.finditer(win):
            m = mm
        # "except as provided in 4.5 (see 3.3)": a second citation introduced by its own cue is a reference, not part of the exception
        if m and not ((len(win[m.end():].split()) > 3 or re.search(r"\d", win[m.end():])) and cues.refcue_end_re.search(win)):
            return "exception_of", m.group(0), "cited_excepts_consumer"
        m = cues.defref_re.search(win) or None
        if m:
            return "definition_of", m.group(0).strip(), ""
        # a definition cue sits right in front of a kind word: "as defined in section 2": the window ends with the cue
        cm = None
        for mm in cues.condition_re.finditer(win):
            cm = mm
        if cm:
            after = win[cm.end():]
            # "where it is shown (see 3.4)": a citation right after a reference cue is a reference, not the condition itself
            if not cues.modal_re.search(after) and not bare_cue and not cues.refcue_end_re.search(win):
                return "condition_from", cm.group(0), ""
        if kind == "table":
            return "table_of", bare_cue or "table", ""
        return "reference", bare_cue or kind, ""

    def add_refs(self, c) -> None:
        cues, ft = self.cues, self.ft
        a, b = c.start, c.end
        seen_spans: list[tuple[int, int]] = []
        found: list[tuple[int, int, str, str, str, str]] = []      # start, end, kind, first, more, bare cue
        for m in cues.ref_re.finditer(ft, a, b):
            kind = cues.kind_of[fold(m.group("kind")).lower().rstrip(".")]
            found.append((m.start(), m.end(), kind, m.group("first"), m.group("more"), ""))
            seen_spans.append((m.start(), m.end()))
        for m in cues.bare_re.finditer(ft, a, b):
            if any(s <= m.start("first") < e for s, e in seen_spans):
                continue
            found.append((m.start("first"), m.end(), "", m.group("first"), m.group("more"), fold(m.group("cue")).lower()))
        for start, end, kind, first, more, bare in sorted(found):
            if start in self.caption_starts or self.is_table_caption(c, start, end, kind, first):
                continue
            if start <= a + 3 and not bare:                  # the clause's own number at its start, not a reference
                own = {lb for _, lb in self.nodes[c.id].labels}
                if norm_label(first)[0] in own or self.nodes[c.id].local:
                    continue
            items = _split_chain(first, more, cues)
            off0 = ft.index(first, start, end) if first in ft[start:end] else start
            for k, (lab, s_off, e_off, _joiner) in enumerate(items):
                s_abs, e_abs = off0 + s_off, off0 + e_off
                # a number after a bare cue that is followed by a unit is a measure ("see 3.5 m"); with a part word it is a label
                unit = cues.unit_re.match(ft[e_abs:e_abs + 12])
                if bare and unit:
                    continue
                # "point 60 inches": a whole number with a unit right after it is a measure even behind a part word ("in" is not
                # counted: "Section 5 in dwellinghouses")
                if unit and unit.group(0).strip().lower() != "in" and re.fullmatch(r"\d+", norm_label(lab)[0]) and kind in ("paragraph", "section"):
                    continue
                # "Building Regulations 2010": a year after a part word is the name of a law, not a label
                if re.fullmatch(r"(?:1[89]|20)\d\d", norm_label(lab)[0]):
                    continue
                # items after the first inherit the kind of the part word
                self.link(c, kind, lab, start, s_abs, e_abs, bare, k, end)

    def link(self, c, kind: str, lab: str, ref_start: int, s: int, e: int, bare: str, k: int, chain_end: int) -> None:
        cues = self.cues
        quote = self.text[(ref_start if k == 0 else s):e]
        ext = self.is_external(ref_start, chain_end)
        etype, cue, direction = self.classify(c, ref_start, kind, bare)
        status, ids, note = self.resolve(c, kind, lab)
        if bare and status == "unresolved":
            return                                           # "see 12" with nothing numbered 12 is a number, not a reference
        if ext and status != "resolved":
            self.edges.append(Edge(etype, None, c.id, c.id, ref_start if k == 0 else s, e, quote, cue, ext, "external", cited=quote))
            return
        if status == "unresolved":
            self.edges.append(Edge(etype, None, c.id, c.id, ref_start if k == 0 else s, e, quote, cue, note, "unresolved", cited=quote))
            return
        target = ids[0]
        if target == c.id:
            return                                           # a clause that names itself
        reason = {"reference": "cites", "table_of": "cites the table", "exception_of": "exception cue",
                  "definition_of": "definition cue", "condition_from": "condition cue"}[etype]
        reason = f'{reason} "{cue}" before "{quote}"' if cue and etype != "reference" else f'{reason} "{quote}"'
        if note:
            reason += f" ({note})"
        if etype == "exception_of" and direction == "consumer_excepts_cited":
            edge = Edge("exception_of", c.id, target, c.id, ref_start if k == 0 else s, e, quote, cue, reason, status, quote, ids)
        else:
            edge = Edge(etype, target, c.id, c.id, ref_start if k == 0 else s, e, quote, cue, reason, status, quote, ids)
        # a table cited in the middle of an exception stays a table edge as well, so that the rows travel with the clause
        self.edges.append(edge)
        if etype in ("exception_of", "condition_from") and self.nodes[target].ntype == "table" and direction != "consumer_excepts_cited":
            self.edges.append(Edge("table_of", target, c.id, c.id, edge.start, edge.end, quote, "table", f'cites the table "{quote}"', status, quote, ids))
        del cues

    # ------------------------------------------------------------------------------------------ exceptions
    def add_exceptions(self) -> None:
        cues = self.cues
        prev: str | None = None
        n_by_clause: dict[str, int] = {}
        for c in self.clauses:
            if c.kind in TABLE_CLAUSES or self.is_listing(c):
                continue
            text = fold(c.text)
            m = cues.exstart_re.match(text[:120])
            if m:
                if prev:
                    cs, ce = c.start + m.start("cue"), c.end
                    nid = f"exc:{c.id}"
                    self.nodes[nid] = Node(nid, "exception", cs, ce, c.id, cue=m.group("cue").lower())
                    self.edges.append(Edge("exception_of", nid, prev, c.id, cs, min(ce, cs + 200), self.text[cs:min(ce, cs + 200)].strip(),
                                           m.group("cue").lower(), f'clause begins with "{m.group("cue")}" and follows {prev}', "resolved", m.group("cue"), [prev]))
                continue
            prev = c.id
            # exception paragraphs written inside the clause: "... Exception 1. Modular furniture ... Exception 2. ..."
            marks = list(cues.exstart_inline_re.finditer(text))
            for i, mk in enumerate(marks):
                cs = c.start + mk.start("cue")
                ce = c.start + (marks[i + 1].start("cue") if i + 1 < len(marks) else len(text))
                k = n_by_clause[c.id] = n_by_clause.get(c.id, 0) + 1
                nid = f"exc:{c.id}#{k}"
                self.nodes[nid] = Node(nid, "exception", cs, ce, c.id, cue=mk.group("cue").lower())
                q = self.text[cs:ce].strip()
                self.edges.append(Edge("exception_of", nid, c.id, c.id, cs, ce, q[:240], mk.group("cue").lower(),
                                       f'paragraph "{mk.group("cue")}" inside the clause', "resolved", mk.group("cue"), [c.id]))
            # an exception in the same sentence: "... unless the stair is external", "except for 4.2"
            inside = [(m_.start(), m_.end()) for m_ in marks]
            for m in cues.exception_re.finditer(text):
                cs = c.start + m.start()
                if any(s <= m.start() < e for s, e in inside):
                    continue
                if any(e.type == "exception_of" and e.evidence_clause == c.id and e.start <= cs < e.end for e in self.edges):
                    continue                                 # already an edge through a reference in this sentence
                if any(e.evidence_clause == c.id and e.start - 80 <= cs <= e.start and e.type == "exception_of" for e in self.edges):
                    continue
                tail = re.search(r"[.;](?=\s|$)|\n\s*\n", text[m.end():])
                ce = c.start + m.end() + (tail.start() if tail else len(text) - m.end())
                if ce - cs < 8:
                    continue
                k = n_by_clause[c.id] = n_by_clause.get(c.id, 0) + 1
                nid = f"exc:{c.id}#{k}"
                self.nodes[nid] = Node(nid, "exception", cs, ce, c.id, cue=m.group(0).lower())
                self.edges.append(Edge("exception_of", nid, c.id, c.id, cs, ce, self.text[cs:ce].strip()[:240], m.group(0).lower(),
                                       f'exception cue "{m.group(0)}" in the clause', "resolved", m.group(0), [c.id]))

    # ------------------------------------------------------------------------------------------ definitions
    def clause_at(self, offset: int) -> str:
        import bisect
        if self._starts is None:
            self._rows = [(c.start, c.end, c.id) for c in self.clauses if c.kind not in TABLE_CLAUSES]
            self._starts = [r[0] for r in self._rows]
        i = bisect.bisect_right(self._starts, offset) - 1
        return self._rows[i][2] if i >= 0 and self._rows[i][1] > offset else ""

    def add_definition(self, term: str, s: int, e: int, cue: str) -> None:
        term = re.sub(r"\s*\([^)]{0,40}\)", "", term).strip(" .,:;“”\"'")
        key = re.sub(r"\s+", " ", fold(term).lower())
        words = key.split()
        if not 1 <= len(words) <= 6 or len(key) < 3 or words[0] in self.cues.term_stop:
            return
        clause = self.clause_at(s)
        nid = f"def:{key}@{clause or s}"
        if nid in self.nodes:
            return
        node = Node(nid, "definition", s, e, clause, term=key, cue=cue)
        self.nodes[nid] = node
        self.terms.setdefault(key, []).append(node)

    def find_definitions(self) -> None:
        """Defined terms, by two shapes only (precision first): a quoted term followed by a definition cue ("'habitable room' means"),
        and the entries of a glossary: a heading that opens a list of definitions, then one entry per paragraph, written either
        "Term.  Definition" or "Term Definition" (a term, then a sentence that starts with a capital)."""
        cues, ft, text = self.cues, self.ft, self.text
        q_open, q_close = "“\"«‘„'", "”\"»’“'"
        quoted = re.compile(rf"[{q_open}]\s*(?P<term>[^{q_close}\n]{{2,50}}?)\s*[{q_close}]\s*(?P<cue>{_alt(cues.raw['definition_cues'])})(?![\w])", re.I)
        for m in quoted.finditer(ft):
            cue = fold(m.group("cue")).lower()
            if cue in cues.weak_defcues:
                continue
            s_end = re.search(r"[.;](?=\s|$)|\n\s*\n", ft[m.end():])
            self.add_definition(text[m.start("term"):m.end("term")], m.start("term"), m.end() + (s_end.end() if s_end else min(len(ft) - m.end(), 300)), cue)
        head = re.compile(rf"(?m)^[^\n]{{0,40}}?(?:{_alt(cues.raw['definition_headings'])})[^\n]{{0,25}}$", re.I)
        kinds_label = rf"(?:{_word_alt(cues.kind_of)})\.?[ \t]*{cues.label_re.pattern}[ \t]*[:.\-][ \t]*[A-Z\d]"
        stop = re.compile(rf"(?m)^[ \t]*(?:(?i:{kinds_label})|\d+(?:\.\d+)+[\t ]+(?=[A-Z]))")
        regions: list[tuple[int, int]] = []
        for m in head.finditer(ft):
            line = ft[m.start():m.end()]
            if len(line.split()) > 8 or re.search(r"\.{4,}|\d\s*$", line) and not re.search(r"[A-Za-z]\.?\s*$", line):
                continue
            a = m.end()
            nxt = stop.search(ft, a + 40)
            end = min(len(ft), a + 80000, nxt.start() if nxt else len(ft))
            if end - a > 80 and not any(a < r1 and end > r0 for r0, r1 in regions):
                regions.append((a, end))
        # the glossary of a document that keeps it in a side column is a clause of kind "definition"; it is not trusted by itself
        bullets = tuple("•▪●\u2013-*")
        skip = _word_alt(cues.raw["annotation_prefixes"])
        for a, b in regions:
            paras = [(a + m.start(), a + m.end()) for m in re.finditer(r"[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*", text[a:b])]
            entries: list[tuple[str, int, str]] = []
            for ps, pe in paras:
                p = text[ps:pe]
                if p.lstrip().startswith(bullets) or re.match(rf"\s*(?:{skip})\b", fold(p), re.I) or re.match(r"\s*\d+\s*$", p) or "\t" in p.split("\n")[0]:
                    continue
                m1 = re.match(r"\s*(?P<term>[A-Z][^.\n]{1,55}?)\.\s{2,}(?=[A-Z0-9])", p) or re.match(r"\s*(?P<term>[A-Z][^.\n]{1,55}?)\.\s*\n\s*(?=[A-Z])", p)
                if not m1:                                   # "Term. Definition" with one space: only for a short term
                    m1 = re.match(r"\s*(?P<term>[A-Z][^.\n]{1,40}?)\.\s+(?=[A-Z])", p)
                    if m1 and len(m1.group("term").split()) > 4:
                        m1 = None
                m2 = re.match(r"\s*(?P<term>[A-Z][\w\-/]*(?:\s+(?:[a-z][\w\-/]*|\([^)]{1,40}\)))*)\s+(?=[A-Z][a-z]*\b)", p)
                m = m1 or m2
                # a definition is a sentence: an index line ("Shooting Facilities") or a heading is not
                if m and (len(p) < 40 or not re.search(r"[.;)]$", p.rstrip())):
                    m = None
                if m:
                    entries.append((ps + m.start("term"), ps, "term." if m1 else "term definition"))
            for k, (ts, _ps, cue) in enumerate(entries):
                te = entries[k + 1][1] if k + 1 < len(entries) else b
                term_end = re.match(r"[^\n]*?(?=\s{2,}|\.\s|\s+[A-Z][a-z]+\b)", text[ts:te])
                term = text[ts:ts + (term_end.end() if term_end else 40)]
                if cue == "term.":
                    term = re.match(r"[^.\n]+", text[ts:te]).group(0)
                else:
                    mm = re.match(r"[A-Z][\w\-/]*(?:\s+(?:[a-z][\w\-/]*|\([^)]{1,40}\)))*", text[ts:te])
                    term = mm.group(0) if mm else term
                self.add_definition(term, ts, te, cue)

    def link_terms(self) -> None:
        if not self.terms:
            return
        cues = self.cues
        by_len = sorted(self.terms, key=lambda k: (-len(k), k))
        pieces = []
        for k in by_len:
            stem = re.escape(k).replace(r"\ ", r"[\s\-]+")
            pieces.append(stem)
        pat = re.compile(rf"(?<![\w])(?:{'|'.join(pieces)})(?:e?s)?(?![\w])", re.I)
        for c in self.clauses:
            if c.kind in TABLE_CLAUSES:
                continue
            if self.is_listing(c):
                continue
            ft = fold(c.text)
            last_end = -1
            used: dict[str, Edge] = {}
            for m in pat.finditer(ft):
                if m.start() < last_end:
                    continue
                key = re.sub(r"[\s\-]+", " ", m.group(0).lower())
                key = key if key in self.terms else (key[:-2] if key[:-2] in self.terms and key.endswith("es") else key[:-1])
                if key not in self.terms:
                    continue
                last_end = m.end()
                defs = [n for n in self.terms[key] if n.clause != c.id]
                if not defs:
                    continue
                if any(n.start <= c.start + m.start() < n.end for n in defs):
                    continue
                n = defs[0]
                if key in used:
                    continue                                 # the first use is the evidence; one edge per term and clause
                s, e = c.start + m.start(), c.start + m.end()
                note = "" if len(defs) == 1 else f" ({len(defs)} definitions of this term; the first is taken)"
                edge = Edge("definition_of", n.id, c.id, c.id, s, e, self.text[s:e], n.cue, f'uses the defined term "{key}"{note}',
                            "resolved" if len(defs) == 1 else "first_of_many", self.text[s:e], [d.id for d in defs])
                used[key] = edge
                self.edges.append(edge)
        del cues

    def is_table_caption(self, c, start: int, end: int, kind: str, first: str) -> bool:
        """A caption line ("Table 217.2 Wheelchair Accessible Telephones") at the start of a line, right above the table of that name."""
        if kind not in ("table", "figure") or (start > c.start and self.ft[start - 1] != "\n"):
            return False
        for cid in self.lookup_global(kind, norm_label(first)[0]):
            n = self.nodes[cid]
            if cid != c.id and 0 <= n.start - end <= 400:
                return True
        return False

    def is_listing(self, c) -> bool:
        """A contents or index clause (a long run of page references and no obligation): it names places, it cites none."""
        if re.search(r"\.{6,}", c.text[:300]) or "[CONTENTS]" in c.id:
            return True
        ft = self.ft[c.start:c.end]
        found = [m.group("first") for m in self.cues.ref_re.finditer(ft)] + [m.group("first") for m in self.cues.bare_re.finditer(ft)]
        distinct = {norm_label(x)[0] for x in found}
        # many different places named in a short text and no obligation: an index. The same table named again and again is not.
        return len(distinct) >= 4 and len(ft.split()) <= 9 * len(found) and not self.cues.modal_re.search(ft)

    def run(self) -> Graph:
        self.make_nodes()
        for c in self.clauses:
            if c.kind != "table_row" and not self.is_listing(c):
                self.add_refs(c)
        n_ref = len(self.edges)
        self.add_exceptions()
        for e in self.edges[n_ref:]:
            e.origin = "exception"
        self.find_definitions()
        n_exc = len(self.edges)
        self.link_terms()
        for e in self.edges[n_exc:]:
            e.origin = "term"
        g = Graph(self.text, self.clauses, self.nodes, self.edges, self.cues, terms=self.terms, clause_by_id=self.by_id)
        g.index()
        return g


def build_graph(text: str, clauses: list, cues: Cues | None = None) -> Graph:
    """The regulation graph of a document: `text` and `clauses` as `rules.clauses.split_document` returns them."""
    return _Builder(text, clauses, cues or load_cues()).run()


# ---------------------------------------------------------------------------------------------------------------- context
@dataclass
class Link:
    type: str
    target: str                       # the clause (or span node) that gives
    target_clause: str
    target_span: tuple[int, int]
    target_text: str
    source_clause: str                # the clause where the words were read
    source_span: tuple[int, int]
    quote: str
    cue: str
    reason: str
    status: str
    via: tuple[str, ...] = ()         # the chain of clauses followed to get here (empty for a direct link)

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


@dataclass
class ResolvedContext:
    clause: str
    references: list[Link] = field(default_factory=list)
    definitions: list[Link] = field(default_factory=list)
    tables: list[Link] = field(default_factory=list)
    exceptions: list[Link] = field(default_factory=list)
    conditions: list[Link] = field(default_factory=list)
    unresolved: list[Link] = field(default_factory=list)
    external: list[Link] = field(default_factory=list)

    def links(self) -> list[Link]:
        return self.references + self.definitions + self.tables + self.exceptions + self.conditions

    def clause_ids(self) -> list[str]:
        """The clauses a reader needs next to this one, in the order of the document, without repeats."""
        seen: dict[str, None] = {}
        for lk in self.links():
            seen.setdefault(lk.target_clause)
        return list(seen)

    def to_dict(self) -> dict:
        return {"clause": self.clause, **{k: [x.to_dict() for x in getattr(self, k)] for k in
                ("references", "definitions", "tables", "exceptions", "conditions", "unresolved", "external")}}


def _link(g: Graph, e: Edge, via: tuple[str, ...] = ()) -> Link:
    n = g.nodes[e.provider] if e.provider else None
    t_text = g.text[n.start:n.end] if n else ""
    return Link(e.type, e.provider or "", n.clause if n else "", (n.start, n.end) if n else (0, 0), t_text[:600], e.evidence_clause,
                (e.start, e.end), e.quote, e.cue, e.reason, e.status, via)


def resolve_context(graph: Graph, clause_id: str, depth: int = 1, max_rows: int = 12) -> ResolvedContext:
    """Everything the document itself says about one clause, read by rules: the clauses it cites, the definitions of the terms it
    uses, the tables it cites (with their rows), the exceptions that attach to it and the clauses that hold its conditions.

    `depth` 2 or more follows the same links from the clauses found (an exception of an exception, a table cited by a cited clause);
    `via` of a link then names the clauses followed. Definitions are never followed further.
    """
    if clause_id not in graph.clause_by_id:
        raise KeyError(clause_id)
    ctx = ResolvedContext(clause_id)
    seen_links: set[tuple[str, str, int]] = set()
    frontier = [(clause_id, ())]
    visited = {clause_id}
    for level in range(max(1, depth)):
        nxt = []
        for cid, via in frontier:
            for e in graph.by_consumer.get(cid, []):
                if e.status in ("unresolved", "external"):
                    if level == 0:
                        (ctx.unresolved if e.status == "unresolved" else ctx.external).append(_link(graph, e, via))
                    continue
                if e.type == "definition_of" and level > 0:
                    continue
                key = (e.type, e.provider or "", e.start)
                if key in seen_links:
                    continue
                seen_links.add(key)
                lk = _link(graph, e, via)
                bucket = {"reference": ctx.references, "definition_of": ctx.definitions, "table_of": ctx.tables,
                          "exception_of": ctx.exceptions, "condition_from": ctx.conditions}[e.type]
                bucket.append(lk)
                if e.provider and graph.nodes[e.provider].clause not in visited and e.type != "definition_of":
                    visited.add(graph.nodes[e.provider].clause)
                    nxt.append((graph.nodes[e.provider].clause, via + (cid,)))
        frontier = nxt
        if not frontier:
            break
    # a table brings its rows: they are the clauses whose parent is the table
    for lk in list(ctx.tables) + [x for x in ctx.references + ctx.exceptions + ctx.conditions if graph.nodes[x.target].ntype == "table"]:
        rows = [c for c in graph.clauses if c.parent == lk.target and c.kind == "table_row"]
        if rows and lk.target_clause == lk.target:
            lk.target_text = (lk.target_text + "\n" + "\n".join(r.text for r in rows[:max_rows]))[:4000]
    return ctx
